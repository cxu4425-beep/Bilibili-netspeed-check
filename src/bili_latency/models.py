"""Data structures shared by the probes, the monitor and the UI."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Deque, Iterable, Optional


@dataclass(frozen=True)
class StreamMeasurement:
    """Result of a single live-stream probe."""

    stream_ms: Optional[float]
    method: str = "none"          # "hls-pdt" | "hls-window" | "flv-keyframe" | "none"
    estimated: bool = True        # False only when a server wall-clock is available
    edge_lag_ms: Optional[float] = None
    buffer_ms: Optional[float] = None
    host: str = ""
    detail: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass(frozen=True)
class NetworkMeasurement:
    """Result of a single network probe."""

    rtt_ms: Optional[float]
    ttfb_ms: Optional[float] = None
    host: str = ""
    clock_offset_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class LatencySample:
    """One point on the timeline shown by the UI.

    ``total_ms`` is the end-to-end estimate: how old the picture on your screen
    is compared to what happened in front of the streamer's camera, limited to
    the parts this tool can actually observe (see docs/METHODOLOGY.md).
    """

    ts: float = field(default_factory=time.time)
    network_ms: Optional[float] = None
    stream_ms: Optional[float] = None
    display_ms: Optional[float] = None
    total_ms: Optional[float] = None
    ok: bool = True
    estimated: bool = True
    method: str = "none"
    host: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[int(pos)]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


class RollingStats:
    """Bounded rolling window over the most recent samples.

    Memory is capped by ``maxlen`` so the process stays flat during multi-day
    sessions.
    """

    def __init__(self, maxlen: int = 180) -> None:
        self.maxlen = max(5, int(maxlen))
        self._samples: Deque[LatencySample] = deque(maxlen=self.maxlen)

    def __len__(self) -> int:
        return len(self._samples)

    def clear(self) -> None:
        self._samples.clear()

    def resize(self, maxlen: int) -> None:
        maxlen = max(5, int(maxlen))
        if maxlen == self.maxlen:
            return
        self.maxlen = maxlen
        self._samples = deque(self._samples, maxlen=maxlen)

    def append(self, sample: LatencySample) -> None:
        self._samples.append(sample)

    @property
    def samples(self) -> list[LatencySample]:
        return list(self._samples)

    def totals(self) -> list[float]:
        return [s.total_ms for s in self._samples if s.ok and s.total_ms is not None]

    def last(self) -> Optional[LatencySample]:
        return self._samples[-1] if self._samples else None

    def avg(self) -> Optional[float]:
        values = self.totals()
        return sum(values) / len(values) if values else None

    def minimum(self) -> Optional[float]:
        values = self.totals()
        return min(values) if values else None

    def maximum(self) -> Optional[float]:
        values = self.totals()
        return max(values) if values else None

    def percentile(self, pct: float) -> Optional[float]:
        return _percentile(self.totals(), pct)

    def jitter(self) -> Optional[float]:
        """Mean absolute difference between consecutive totals (RFC 3550 style)."""
        values = self.totals()
        if len(values) < 2:
            return None
        diffs = [abs(b - a) for a, b in zip(values, values[1:])]
        return sum(diffs) / len(diffs)

    def failure_rate(self) -> float:
        if not self._samples:
            return 0.0
        failed = sum(1 for s in self._samples if not s.ok)
        return failed / len(self._samples)

    def spark_values(self, count: int) -> list[Optional[float]]:
        """Last ``count`` totals, ``None`` where a probe failed (for the sparkline)."""
        recent = list(self._samples)[-count:]
        return [s.total_ms if s.ok else None for s in recent]

    def extend(self, samples: Iterable[LatencySample]) -> None:
        for sample in samples:
            self.append(sample)
