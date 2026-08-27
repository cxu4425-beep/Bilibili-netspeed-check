"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

from . import APP_NAME, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bili-latency",
        description=f"{APP_NAME} - measure Bilibili live delay from server to client to screen.",
    )
    parser.add_argument("--room", metavar="ID_OR_URL", help="live room id or URL to monitor")
    parser.add_argument("--video", metavar="ID_OR_URL", help="video (BV/av id or URL) to monitor")
    parser.add_argument("--detect", dest="detect", action="store_true",
                        help="follow whatever Bilibili page you are watching")
    parser.add_argument("--no-detect", dest="detect", action="store_false",
                        help="never auto-detect; use --room / --video only")
    parser.set_defaults(detect=None)
    parser.add_argument("--lang", choices=["auto", "zh_CN", "zh_TW", "en"], help="interface language")
    parser.add_argument("--config-dir", metavar="PATH", help="use this folder for config and logs")
    parser.add_argument("--reset-config", action="store_true", help="start from default settings")
    parser.add_argument("--no-tray", action="store_true", help="do not create a tray icon")
    parser.add_argument("--no-overlay", action="store_true", help="start with the overlay hidden")
    parser.add_argument(
        "--probe-once", action="store_true",
        help="run a single measurement, print it as JSON and exit (no window)",
    )
    parser.add_argument(
        "--detect-report", action="store_true",
        help="print what each detection source can see on this machine, then exit",
    )
    parser.add_argument(
        "--client-dir", action="append", metavar="PATH", default=None,
        help="extra folder to search for the desktop client's data (repeatable)",
    )
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="logging verbosity")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    if args.config_dir:
        os.environ["BILI_LATENCY_CONFIG_DIR"] = args.config_dir

    # Imported after the config dir override so paths resolve correctly.
    from .config import Config, parse_room_id
    from .i18n import set_language
    from .logging_setup import setup_logging

    setup_logging(getattr(logging, args.log_level, logging.INFO))
    log = logging.getLogger(__name__)

    config = Config() if args.reset_config else Config.load()
    if args.room:
        room = parse_room_id(args.room)
        if not room:
            print(f"not a room id or live URL: {args.room}", file=sys.stderr)
            return 2
        config.room_id = room
        config.manual_kind = "live"
        config.detect.enabled = False
    if args.video:
        from .probes.video import parse_video_target

        video, page = parse_video_target(args.video)
        if not video:
            print(f"not a video id or URL: {args.video}", file=sys.stderr)
            return 2
        config.video_id = video
        config.video_page = page
        config.manual_kind = "video"
        config.detect.enabled = False
    if args.detect is not None:
        config.detect.enabled = args.detect
    if args.client_dir:
        config.detect.client_dirs = list(dict.fromkeys(config.detect.client_dirs + args.client_dir))
    if args.lang:
        config.language = args.lang
    if args.no_tray:
        config.tray.enabled = False
    if args.no_overlay:
        config.overlay.enabled = False
    config = config.sanitized()
    set_language(config.language)

    if args.detect_report:
        return _detect_report(config)

    if args.probe_once:
        return _probe_once(config)

    from PySide6.QtWidgets import QApplication  # noqa: F401  (imported for side effects)

    from .app import MonitorApplication, create_application
    from .single_instance import SingleInstance

    app = create_application(sys.argv[:1])

    # Checked before anything is built, so a second launch never flashes a
    # second tray icon - it just brings the running copy back into view.
    guard = SingleInstance()
    if guard.notify_running_instance():
        log.info("another instance is already running; asked it to show itself")
        print(f"{APP_NAME} is already running.", file=sys.stderr)
        return 0
    guard.listen()

    monitor = MonitorApplication(app, config, guard)
    monitor.start()
    return app.exec()


def _probe_once(config) -> int:
    """Headless single measurement - handy for troubleshooting and scripting."""
    from .models import KIND_NETWORK, KIND_VIDEO, LatencySample
    from .probes.network import HttpClient, tcp_rtt_ms
    from .probes.stream import StreamProbe
    from .probes.video import VideoProbe

    target = _probe_target(config)
    timeout_s = config.probe.timeout_ms / 1000.0
    client = HttpClient(timeout_s=timeout_s)
    try:
        rtt = tcp_rtt_ms(config.probe.rtt_host, config.probe.rtt_port, timeout_s)
        if target.kind == KIND_NETWORK:
            sample = LatencySample(
                network_ms=rtt, total_ms=rtt, ok=rtt is not None, kind=KIND_NETWORK,
                method="network-only", host=config.probe.rtt_host,
                error=None if rtt is not None else "network unreachable",
            )
        else:
            if target.kind == KIND_VIDEO:
                probe = VideoProbe(client, playurl_refresh_s=config.probe.playurl_refresh_s)
                result = probe.measure(target.ident, target.page)
            else:
                probe = StreamProbe(
                    client,
                    prefer_hls=config.probe.prefer_hls,
                    player_buffer_segments=config.probe.player_buffer_segments,
                    playurl_refresh_s=config.probe.playurl_refresh_s,
                )
                measurement = client.measure(
                    "https://api.live.bilibili.com/room/v1/Room/get_info?room_id=1"
                )
                probe.set_clock_offset_ms(measurement.clock_offset_ms)
                result = probe.measure(target.ident)
            sample = LatencySample(
                network_ms=probe.endpoint_rtt_ms(timeout_s) or rtt,
                stream_ms=result.stream_ms,
                total_ms=result.stream_ms,
                ok=result.stream_ms is not None,
                estimated=result.estimated,
                kind=target.kind,
                method=result.method,
                host=result.host,
                title=result.title or target.title,
                source=target.source,
                throughput_mbps=result.throughput_mbps,
                required_mbps=result.required_mbps,
                error=result.error,
            )
        payload = sample.to_dict()
        payload["target"] = {"kind": target.kind, "id": target.ident, "page": target.page,
                             "source": target.source}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if sample.ok else 1
    finally:
        client.close()


def _detect_report(config) -> int:
    """Show what each detection source finds here - the first thing to run when
    auto-detection is not picking up the desktop client."""
    from .config import title_memory_path
    from .detect import AutoDetector

    detector = AutoDetector(config.detect, memory_path=title_memory_path())
    try:
        report = detector.report()
    finally:
        detector.close()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["client"]["folders"]:
        print(
            "\nNo desktop-client data folder found. If the client is installed, pass its\n"
            "folder with --client-dir (e.g. --client-dir \"%APPDATA%\\bilibili\") and\n"
            "report the path so it can be added to the defaults.",
            file=sys.stderr,
        )
    return 0 if report.get("result") else 1


def _probe_target(config):
    """Same target rules as the GUI: detected first, configured second."""
    from .detect import AutoDetector
    from .models import KIND_LIVE, KIND_NETWORK, KIND_VIDEO, WatchTarget

    if config.detect.enabled:
        detector = AutoDetector(config.detect)
        try:
            detected = detector.poll(force=True)
        finally:
            detector.close()
        if detected is not None and not detected.is_empty:
            if detected.kind != KIND_VIDEO or config.detect.follow_videos:
                return detected

    if config.manual_kind == KIND_VIDEO and config.video_id:
        return WatchTarget(kind=KIND_VIDEO, ident=config.video_id, page=config.video_page,
                               source="manual")
    if config.room_id:
        return WatchTarget(kind=KIND_LIVE, ident=config.room_id, source="manual")
    if config.video_id:
        return WatchTarget(kind=KIND_VIDEO, ident=config.video_id, page=config.video_page,
                               source="manual")
    return WatchTarget(kind=KIND_NETWORK, source="manual")
