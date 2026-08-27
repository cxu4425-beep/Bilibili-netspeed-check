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
    parser.add_argument("--lang", choices=["auto", "zh_CN", "zh_TW", "en"], help="interface language")
    parser.add_argument("--config-dir", metavar="PATH", help="use this folder for config and logs")
    parser.add_argument("--reset-config", action="store_true", help="start from default settings")
    parser.add_argument("--no-tray", action="store_true", help="do not create a tray icon")
    parser.add_argument("--no-overlay", action="store_true", help="start with the overlay hidden")
    parser.add_argument(
        "--probe-once", action="store_true",
        help="run a single measurement, print it as JSON and exit (no window)",
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
    if args.lang:
        config.language = args.lang
    if args.no_tray:
        config.tray.enabled = False
    if args.no_overlay:
        config.overlay.enabled = False
    config = config.sanitized()
    set_language(config.language)

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
    """Headless single measurement - handy for troubleshooting and CI."""
    from .models import LatencySample
    from .probes.network import HttpClient, tcp_rtt_ms
    from .probes.stream import StreamProbe

    timeout_s = config.probe.timeout_ms / 1000.0
    client = HttpClient(timeout_s=timeout_s)
    try:
        rtt = tcp_rtt_ms(config.probe.rtt_host, config.probe.rtt_port, timeout_s)
        if not config.room_id:
            sample = LatencySample(
                network_ms=rtt, total_ms=rtt, ok=rtt is not None, method="network-only",
                host=config.probe.rtt_host,
                error=None if rtt is not None else "network unreachable",
            )
        else:
            probe = StreamProbe(
                client,
                prefer_hls=config.probe.prefer_hls,
                player_buffer_segments=config.probe.player_buffer_segments,
                playurl_refresh_s=config.probe.playurl_refresh_s,
            )
            measurement = client.measure("https://api.live.bilibili.com/room/v1/Room/get_info?room_id=1")
            probe.set_clock_offset_ms(measurement.clock_offset_ms)
            result = probe.measure(config.room_id)
            sample = LatencySample(
                network_ms=probe.endpoint_rtt_ms(timeout_s) or rtt,
                stream_ms=result.stream_ms,
                total_ms=result.stream_ms,
                ok=result.stream_ms is not None,
                estimated=result.estimated,
                method=result.method,
                host=result.host,
                error=result.error,
            )
        print(json.dumps(sample.to_dict(), indent=2, ensure_ascii=False))
        return 0 if sample.ok else 1
    finally:
        client.close()
