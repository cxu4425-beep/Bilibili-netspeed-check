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
        prog="lagscope",
        description=f"{APP_NAME} - measure Bilibili live delay from server to client to screen.",
    )
    parser.add_argument("--room", metavar="ID_OR_URL", help="live room id or URL to monitor")
    parser.add_argument("--video", metavar="ID_OR_URL", help="video (BV/av id or URL) to monitor")
    parser.add_argument("--app", metavar="NAME", help="measure any application by process name")
    parser.add_argument("--app-foreground", action="store_true",
                        help="measure whichever application is in the foreground")
    parser.add_argument("--ping", metavar="HOST", help="measure a server address directly")
    parser.add_argument("--ping-port", type=int, default=None, metavar="PORT",
                        help="port to use with --ping (default 443)")
    parser.add_argument("--list-apps", action="store_true",
                        help="list the applications that currently hold connections, then exit")
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
        os.environ["LAGSCOPE_CONFIG_DIR"] = args.config_dir

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
    if args.app or args.app_foreground:
        config.manual_kind = "app"
        config.app_name = args.app or ""
        config.app_follow_foreground = bool(args.app_foreground)
        config.detect.enabled = False
    if args.ping:
        config.manual_kind = "target"
        config.target_host = args.ping
        if args.ping_port:
            config.target_port = args.ping_port
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

    if args.list_apps:
        return _list_apps()

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
    from .models import KIND_APP, KIND_NETWORK, KIND_TARGET, KIND_VIDEO, LatencySample
    from .probes.network import HttpClient, tcp_rtt_ms
    from .probes.stream import StreamProbe
    from .probes.video import VideoProbe

    target = _probe_target(config)
    timeout_s = config.probe.timeout_ms / 1000.0
    client = HttpClient(timeout_s=timeout_s)
    try:
        if target.kind == KIND_APP:
            from .probes.appnet import AppNetProbe

            result = AppNetProbe().measure(target.ident, timeout_s)
            sample = LatencySample(
                network_ms=result.rtt_ms, total_ms=result.rtt_ms, ok=result.rtt_ms is not None,
                kind=KIND_APP, method=result.method, title=target.ident,
                host=str(result.peer) if result.peer else "",
                connections=result.connections, error=result.error,
            )
            print(json.dumps(_with_target(sample, target), indent=2, ensure_ascii=False))
            return 0 if sample.ok else 1

        if target.kind == KIND_TARGET:
            from .probes.network import icmp_ping_ms

            port = int(target.page or 443)
            rtt = tcp_rtt_ms(target.ident, port, timeout_s)
            method = "tcp" if rtt is not None else "icmp"
            if rtt is None:
                rtt = icmp_ping_ms(target.ident, timeout_s)
            sample = LatencySample(
                network_ms=rtt, total_ms=rtt, ok=rtt is not None, kind=KIND_TARGET,
                method=method if rtt is not None else "none",
                host=f"{target.ident}:{port}", title=target.ident,
                error=None if rtt is not None else "unreachable",
            )
            print(json.dumps(_with_target(sample, target), indent=2, ensure_ascii=False))
            return 0 if sample.ok else 1

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
        print(json.dumps(_with_target(sample, target), indent=2, ensure_ascii=False))
        return 0 if sample.ok else 1
    finally:
        client.close()


def _list_apps() -> int:
    """Show which programs are on the network, so one can be named with --app."""
    from .probes.appnet import list_apps

    apps = list_apps()
    if not apps:
        print("No application with open connections was found.", file=sys.stderr)
        return 1
    width = max(len(app.name) for app in apps)
    print(f"{'APPLICATION'.ljust(width)}  SOCKETS  PIDS")
    for app in apps:
        pids = ",".join(str(pid) for pid in app.pids[:4])
        print(f"{app.name.ljust(width)}  {app.connections:>7}  {pids}")
    return 0


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


def _with_target(sample, target) -> dict:
    payload = sample.to_dict()
    payload["target"] = {"kind": target.kind, "id": target.ident, "page": target.page,
                         "source": target.source}
    return payload


def _probe_target(config):
    """Same rules the GUI uses, with detection resolved right now."""
    from .detect import AutoDetector
    from .targets import resolve_target

    def foreground_app() -> str:
        from .ui.anchor import create_window_finder

        return create_window_finder().foreground_process()

    detector = None
    if config.detect.enabled:
        detector = AutoDetector(config.detect)
    try:
        return resolve_target(config, detector, foreground_app, force_detect=True)
    finally:
        if detector is not None:
            detector.close()

