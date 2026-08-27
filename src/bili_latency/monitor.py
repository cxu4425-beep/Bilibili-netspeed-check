"""The monitoring loop.

Runs in its own QThread so that a slow network never freezes the overlay. One
round performs: TCP RTT -> live-stream probe -> combine with the display
estimate the UI thread keeps updated -> emit a LatencySample.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .config import Config
from .models import LatencySample
from .probes.network import HttpClient, tcp_rtt_ms
from .probes.stream import RoomInfo, StreamProbe

LOG = logging.getLogger(__name__)

CLOCK_SYNC_INTERVAL_S = 60.0
CLOCK_SYNC_URL = "https://api.live.bilibili.com/room/v1/Room/get_info?room_id=1"

STATUS_OK = "ok"
STATUS_OFFLINE = "offline"
STATUS_NO_ROOM = "no_room"
STATUS_ERROR = "error"
STATUS_PAUSED = "paused"


class MonitorWorker(QObject):
    """Lives in the worker thread; owns the HTTP client and the probes."""

    sampleReady = Signal(object)      # LatencySample
    statusChanged = Signal(str, str)  # status key, detail text
    roomInfoChanged = Signal(object)  # RoomInfo | None

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._lock = threading.Lock()
        self._display_ms: Optional[float] = None
        self._paused = False
        self._running = False
        self._failures = 0
        self._last_clock_sync = 0.0
        self._last_status = ""
        self._client: Optional[HttpClient] = None
        self._stream: Optional[StreamProbe] = None
        self._timer: Optional[QTimer] = None

    # ------------------------------------------------------------- lifecycle
    @Slot()
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._build_probes()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        self._timer.start(0)
        LOG.info("monitor started")

    @Slot()
    def stop(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.stop()
        if self._client is not None:
            self._client.close()
        LOG.info("monitor stopped")

    @Slot(object)
    def applyConfig(self, config: Config) -> None:
        with self._lock:
            self._config = config
        self._build_probes()
        self._failures = 0
        if self._running and self._timer is not None:
            self._timer.start(0)

    @Slot(bool)
    def setPaused(self, paused: bool) -> None:
        self._paused = bool(paused)
        if not paused and self._running and self._timer is not None:
            self._timer.start(0)
        if paused:
            self._emit_status(STATUS_PAUSED, "")

    def setDisplayLatency(self, display_ms: Optional[float]) -> None:
        """Thread-safe hand-off of the UI thread's display estimate."""
        with self._lock:
            self._display_ms = display_ms

    # ---------------------------------------------------------------- helpers
    def _build_probes(self) -> None:
        with self._lock:
            config = self._config
        timeout_s = config.probe.timeout_ms / 1000.0
        if self._client is None:
            self._client = HttpClient(timeout_s=timeout_s)
        else:
            self._client.timeout_s = timeout_s
            self._client.recycle()
        self._stream = StreamProbe(
            self._client,
            prefer_hls=config.probe.prefer_hls,
            player_buffer_segments=config.probe.player_buffer_segments,
            playurl_refresh_s=config.probe.playurl_refresh_s,
        )
        self._stream.set_room(config.room_id)
        self._last_clock_sync = 0.0

    def _schedule_next(self, failed: bool) -> None:
        if not self._running or self._timer is None:
            return
        with self._lock:
            config = self._config
        interval = config.probe.interval_ms
        if failed:
            self._failures = min(self._failures + 1, 16)
            multiplier = min(2 ** self._failures, config.probe.max_backoff_multiplier)
            interval = int(interval * multiplier)
        else:
            self._failures = 0
        self._timer.start(max(200, interval))

    def _emit_status(self, status: str, detail: str) -> None:
        if status != self._last_status or detail:
            self._last_status = status
            self.statusChanged.emit(status, detail)

    # ------------------------------------------------------------------ round
    @Slot()
    def _tick(self) -> None:
        if not self._running:
            return
        if self._paused:
            self._schedule_next(False)
            return
        try:
            sample = self._run_round()
        except Exception as exc:  # never let the loop die on a bad round
            LOG.exception("probe round failed")
            sample = LatencySample(ok=False, error=str(exc)[:200])
        self.sampleReady.emit(sample)
        self._schedule_next(failed=not sample.ok)

    def _run_round(self) -> LatencySample:
        with self._lock:
            config = self._config
            display_ms = self._display_ms
        assert self._client is not None and self._stream is not None

        timeout_s = config.probe.timeout_ms / 1000.0
        self._sync_clock_if_due(timeout_s)

        rtt_ms = self._stream.endpoint_rtt_ms(timeout_s)
        if rtt_ms is None:
            rtt_ms = tcp_rtt_ms(config.probe.rtt_host, config.probe.rtt_port, timeout_s)

        include_display = config.display.include_in_total
        display_component = display_ms if (include_display and display_ms is not None) else None

        if not config.room_id:
            total = None if rtt_ms is None else rtt_ms + (display_component or 0.0)
            self._emit_status(STATUS_NO_ROOM if rtt_ms is not None else STATUS_ERROR, "")
            return LatencySample(
                network_ms=rtt_ms,
                display_ms=display_ms,
                total_ms=total,
                ok=rtt_ms is not None,
                estimated=True,
                method="network-only",
                host=config.probe.rtt_host,
                error=None if rtt_ms is not None else "network unreachable",
            )

        measurement = self._stream.measure(config.room_id)
        self.roomInfoChanged.emit(self._stream.room_info)

        if measurement.stream_ms is None:
            status = STATUS_OFFLINE if measurement.error == "offline" else STATUS_ERROR
            self._emit_status(status, measurement.error or "")
            return LatencySample(
                network_ms=rtt_ms,
                display_ms=display_ms,
                total_ms=None,
                ok=False,
                method=measurement.method,
                host=measurement.host,
                error=measurement.error,
            )

        # The stream figure is already client-side elapsed time (it contains the
        # network transit), so the network RTT is reported, not added again.
        total = measurement.stream_ms + (display_component or 0.0)
        self._emit_status(STATUS_OK, "")
        return LatencySample(
            network_ms=rtt_ms,
            stream_ms=measurement.stream_ms,
            display_ms=display_ms,
            total_ms=total,
            ok=True,
            estimated=measurement.estimated,
            method=measurement.method,
            host=measurement.host,
        )

    def _sync_clock_if_due(self, timeout_s: float) -> None:
        now = time.monotonic()
        if now - self._last_clock_sync < CLOCK_SYNC_INTERVAL_S:
            return
        self._last_clock_sync = now
        assert self._client is not None and self._stream is not None
        try:
            measurement = self._client.measure(CLOCK_SYNC_URL)
            if measurement.clock_offset_ms is not None:
                self._stream.set_clock_offset_ms(measurement.clock_offset_ms)
                LOG.debug("clock offset %.0f ms", measurement.clock_offset_ms)
        except Exception as exc:  # a failed sync just keeps the previous offset
            LOG.debug("clock sync failed: %s", exc)


__all__ = [
    "MonitorWorker",
    "RoomInfo",
    "STATUS_ERROR",
    "STATUS_NO_ROOM",
    "STATUS_OFFLINE",
    "STATUS_OK",
    "STATUS_PAUSED",
]
