"""Spotting the moments that matter: stalls, spikes and recoveries.

A number that is bad *right now* is easy to see on the overlay. What people
actually remember is "it hiccuped four times this evening", so every failed
probe and every sudden jump is recorded as an event, counted over a rolling
window, and optionally announced once (never once per sample).
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .models import LatencySample

STALL = "stall"        # the probe failed outright: stream down, app unreachable
SPIKE = "spike"        # latency jumped far above its recent normal


@dataclass(frozen=True)
class Event:
    kind: str
    ts: float
    value_ms: Optional[float] = None
    baseline_ms: Optional[float] = None
    detail: str = ""


class EventLog:
    """Rolling record of stalls and spikes over the last ``window_s`` seconds."""

    def __init__(self, window_s: float = 3600.0, spike_factor: float = 2.0,
                 min_baseline_samples: int = 10, maxlen: int = 500) -> None:
        self.window_s = max(60.0, float(window_s))
        self.spike_factor = max(1.2, float(spike_factor))
        self.min_baseline_samples = max(3, int(min_baseline_samples))
        self._events: Deque[Event] = deque(maxlen=maxlen)
        self._recent: Deque[float] = deque(maxlen=60)
        self._in_stall = False
        self._in_spike = False

    # ------------------------------------------------------------------ input
    def observe(self, sample: LatencySample) -> Optional[Event]:
        """Feed one sample; returns a new event when this sample starts one."""
        now = sample.ts or time.time()
        event: Optional[Event] = None

        if not sample.ok:
            # Only the first failure of a run is an event, not every retry.
            if not self._in_stall:
                event = Event(kind=STALL, ts=now, detail=(sample.error or "")[:120])
                self._events.append(event)
            self._in_stall = True
            self._in_spike = False
            return event

        self._in_stall = False
        value = sample.total_ms
        if value is None:
            return None

        baseline = self.baseline()
        if baseline is not None and value > baseline * self.spike_factor:
            if not self._in_spike:
                event = Event(kind=SPIKE, ts=now, value_ms=value, baseline_ms=baseline)
                self._events.append(event)
            self._in_spike = True
        else:
            self._in_spike = False
            # A spike must not poison the baseline it is measured against.
            self._recent.append(value)
        return event

    def baseline(self) -> Optional[float]:
        """Median of the recent healthy samples."""
        if len(self._recent) < self.min_baseline_samples:
            return None
        return statistics.median(self._recent)

    # ----------------------------------------------------------------- output
    def _fresh(self) -> list:
        cutoff = time.time() - self.window_s
        return [event for event in self._events if event.ts >= cutoff]

    def count(self, kind: Optional[str] = None) -> int:
        return sum(1 for event in self._fresh() if kind is None or event.kind == kind)

    def last(self) -> Optional[Event]:
        events = self._fresh()
        return events[-1] if events else None

    def summary(self) -> dict:
        events = self._fresh()
        last = events[-1] if events else None
        return {
            "window_min": int(self.window_s / 60),
            "stalls": sum(1 for event in events if event.kind == STALL),
            "spikes": sum(1 for event in events if event.kind == SPIKE),
            "baseline_ms": self.baseline(),
            "last": None if last is None else {
                "kind": last.kind,
                "ago_s": round(max(0.0, time.time() - last.ts), 1),
                "value_ms": last.value_ms,
            },
        }

    def clear(self) -> None:
        self._events.clear()
        self._recent.clear()
        self._in_stall = False
        self._in_spike = False


class Notifier:
    """Rate limit for tray notifications: at most one per ``cooldown_s``."""

    def __init__(self, cooldown_s: float = 300.0) -> None:
        self.cooldown_s = max(30.0, float(cooldown_s))
        self._last_sent = 0.0

    def should_notify(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        if now - self._last_sent < self.cooldown_s:
            return False
        self._last_sent = now
        return True

    def reset(self) -> None:
        self._last_sent = 0.0
