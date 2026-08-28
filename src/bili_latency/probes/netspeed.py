"""Whole-machine network throughput.

Every sample carries the current upload/download speed, whatever is being
monitored - it is the number people actually want next to a latency figure
("is something else eating my line right now?").

Counters come from psutil, so this works the same on Windows, macOS and Linux.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a hard dependency
    psutil = None  # type: ignore

LOG = logging.getLogger(__name__)

# Virtual adapters that would double-count real traffic.
_SKIP_PREFIXES = ("lo", "veth", "docker", "br-", "utun", "ifb", "bridge", "vmnet", "vboxnet")


@dataclass(frozen=True)
class NetSpeed:
    up_mbps: Optional[float] = None
    down_mbps: Optional[float] = None
    up_bytes: int = 0
    down_bytes: int = 0
    interval_s: float = 0.0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.up_mbps is not None and self.down_mbps is not None


def _is_real_nic(name: str) -> bool:
    lowered = name.lower()
    return not any(lowered.startswith(prefix) for prefix in _SKIP_PREFIXES)


class NetSpeedProbe:
    """Turns cumulative interface counters into a rate.

    The first sample only sets the baseline, so it reports nothing; every later
    one covers the time since the previous call.
    """

    def __init__(self) -> None:
        self._last_sent = 0
        self._last_recv = 0
        self._last_ts = 0.0
        self._primed = False

    def reset(self) -> None:
        self._primed = False

    def _totals(self) -> Optional[tuple]:
        if psutil is None:
            return None
        try:
            counters = psutil.net_io_counters(pernic=True)
        except Exception as exc:  # pragma: no cover - platform dependent
            LOG.debug("net counters unavailable: %s", exc)
            return None
        sent = recv = 0
        for name, entry in counters.items():
            if not _is_real_nic(name):
                continue
            sent += entry.bytes_sent
            recv += entry.bytes_recv
        return sent, recv

    def sample(self) -> NetSpeed:
        totals = self._totals()
        now = time.monotonic()
        if totals is None:
            return NetSpeed(error="counters unavailable")
        sent, recv = totals

        if not self._primed:
            self._last_sent, self._last_recv, self._last_ts = sent, recv, now
            self._primed = True
            return NetSpeed()

        interval = now - self._last_ts
        if interval <= 0.05:
            return NetSpeed()
        up_bytes = max(0, sent - self._last_sent)
        down_bytes = max(0, recv - self._last_recv)
        # A counter reset (adapter reconnected) shows up as a negative delta.
        if sent < self._last_sent or recv < self._last_recv:
            self._last_sent, self._last_recv, self._last_ts = sent, recv, now
            return NetSpeed()

        self._last_sent, self._last_recv, self._last_ts = sent, recv, now
        return NetSpeed(
            up_mbps=(up_bytes * 8) / interval / 1_000_000.0,
            down_mbps=(down_bytes * 8) / interval / 1_000_000.0,
            up_bytes=up_bytes,
            down_bytes=down_bytes,
            interval_s=interval,
        )
