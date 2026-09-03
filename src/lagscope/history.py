"""Long-term history: what the connection looked like over hours and days.

The overlay answers "how is it right now" and the rolling window answers "how
has it been for the last few minutes". Neither answers the question people
actually take to a helpdesk or a forum:

    "it was fine all afternoon and then fell apart around nine last night"

Storing every sample would be the obvious way to answer that, and the wrong
one: a two second interval is 43,200 samples a day. Instead each minute is
summarised into one bucket - average, best, worst, p95, jitter, how many
probes failed - which is 1,440 rows a day, small enough to keep on disk, load
instantly and draw without thinning.

The file is rewritten atomically and a damaged one is discarded rather than
allowed to stop the app from starting: history is nice to have, never load
bearing.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Deque, Iterable, List, Optional

from .config import app_config_dir
from .models import LatencySample

LOG = logging.getLogger(__name__)

DEFAULT_BUCKET_S = 60
DEFAULT_KEEP_HOURS = 168      # a week, so a weekly pattern can exist at all
FILE_VERSION = 1
# Guards against a pathological interval filling memory inside one bucket.
MAX_VALUES_PER_BUCKET = 4000
MAX_MARKERS = 50
# A comparison window is capped so "before" cannot stretch back over a whole
# different evening, and floored so it is never a couple of minutes of noise.
MAX_COMPARE_SPAN_S = 6 * 3600
MIN_COMPARE_BUCKETS = 5


@dataclass(frozen=True)
class Bucket:
    """One minute of measurements, already summarised."""

    start: float                    # unix time, aligned to the bucket size
    count: int = 0                  # probes attempted
    ok: int = 0                     # probes that answered
    avg_ms: Optional[float] = None
    min_ms: Optional[float] = None
    max_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    stalls: int = 0
    spikes: int = 0
    kind: str = ""
    label: str = ""
    # What an automatic check blamed, if one ran in this minute. This is what
    # turns "it stalled at 21:14" into "it stalled at 21:14 - weak Wi-Fi".
    verdict: str = ""
    verdict_detail: str = ""
    # Which edge served this minute. Kept because "why is it sometimes bad"
    # is usually "which machine was I given", and that answer is unanswerable
    # after the fact unless it was written down at the time.
    host: str = ""
    # Which wireless link carried this minute, and how well. Recorded for the
    # same reason as the edge above: "why is it sometimes bad" is often "which
    # radio was I on", and that cannot be recovered after the fact.
    link: str = ""
    signal_pct: Optional[int] = None
    # How many times the access point changed inside this minute. With a mesh
    # the SSID never changes, so a roam is invisible without this - and a roam
    # mid-stream is a stall with no other explanation.
    roams: int = 0

    @property
    def loss_pct(self) -> float:
        if not self.count:
            return 0.0
        return (self.count - self.ok) * 100.0 / self.count

    def as_row(self) -> list:
        """Compact form used on disk: order matters, see ``from_row``."""
        return [
            round(self.start, 1), self.count, self.ok,
            _round(self.avg_ms), _round(self.min_ms), _round(self.max_ms),
            _round(self.p95_ms), _round(self.jitter_ms),
            self.stalls, self.spikes, self.kind, self.label,
            self.verdict, self.verdict_detail, self.host,
            self.link, "" if self.signal_pct is None else self.signal_pct, self.roams,
        ]

    @classmethod
    def from_row(cls, row: Iterable) -> Optional["Bucket"]:
        try:
            values = list(row)
            if len(values) < 10:
                return None
            return cls(
                start=float(values[0]), count=int(values[1]), ok=int(values[2]),
                avg_ms=_opt_float(values[3]), min_ms=_opt_float(values[4]),
                max_ms=_opt_float(values[5]), p95_ms=_opt_float(values[6]),
                jitter_ms=_opt_float(values[7]),
                stalls=int(values[8]), spikes=int(values[9]),
                kind=str(values[10]) if len(values) > 10 else "",
                label=str(values[11]) if len(values) > 11 else "",
                # Written since 3.6; rows from an older file simply lack them.
                verdict=str(values[12]) if len(values) > 12 else "",
                verdict_detail=str(values[13]) if len(values) > 13 else "",
                # Written since 4.7; older rows simply have no edge recorded.
                host=str(values[14]) if len(values) > 14 else "",
                link=str(values[15]) if len(values) > 15 else "",
                signal_pct=_optional_int(values[16]) if len(values) > 16 else None,
                roams=int(values[17] or 0) if len(values) > 17 else 0,
            )
        except (TypeError, ValueError):
            return None

    def as_dict(self) -> dict:
        return {
            "start": self.start, "count": self.count, "ok": self.ok,
            "loss_pct": round(self.loss_pct, 1),
            "avg_ms": self.avg_ms, "min_ms": self.min_ms, "max_ms": self.max_ms,
            "p95_ms": self.p95_ms, "jitter_ms": self.jitter_ms,
            "stalls": self.stalls, "spikes": self.spikes,
            "kind": self.kind, "label": self.label,
            "verdict": self.verdict, "verdict_detail": self.verdict_detail,
            "host": self.host,
            "link": self.link,
            "signal_pct": self.signal_pct,
            "roams": self.roams,
        }


class _OpenBucket:
    """The minute currently being filled in."""

    def __init__(self, start: float) -> None:
        self.start = start
        self.values: List[float] = []
        self.count = 0
        self.ok = 0
        self.stalls = 0
        self.spikes = 0
        self.kind = ""
        self.label = ""
        self.verdict = ""
        self.verdict_detail = ""
        # A minute can straddle a CDN switch, so the edge that served most of
        # it wins rather than whichever happened to be last.
        self.hosts: dict = {}
        self.links: dict = {}
        self.signals: list = []
        self.last_bssid = ""
        self.roams = 0

    def add(self, sample: LatencySample) -> None:
        self.count += 1
        if sample.ok and sample.total_ms is not None:
            self.ok += 1
            if len(self.values) < MAX_VALUES_PER_BUCKET:
                self.values.append(float(sample.total_ms))
        if sample.kind:
            self.kind = sample.kind
        title = sample.title or sample.host
        if title:
            self.label = title[:80]
        if sample.host:
            self.hosts[sample.host] = self.hosts.get(sample.host, 0) + 1
        if sample.link:
            self.links[sample.link] = self.links.get(sample.link, 0) + 1
        if sample.signal_pct is not None:
            self.signals.append(int(sample.signal_pct))
        if sample.bssid:
            # Only a change between two known APs counts. Arriving at the first
            # one is not a roam, and neither is the radio briefly saying
            # nothing while it reassociates.
            if self.last_bssid and sample.bssid != self.last_bssid:
                self.roams += 1
            self.last_bssid = sample.bssid

    def close(self) -> Bucket:
        values = self.values
        jitter = None
        if len(values) > 1:
            jitter = sum(abs(b - a) for a, b in zip(values, values[1:])) / (len(values) - 1)
        return Bucket(
            start=self.start, count=self.count, ok=self.ok,
            avg_ms=(sum(values) / len(values)) if values else None,
            min_ms=min(values) if values else None,
            max_ms=max(values) if values else None,
            p95_ms=percentile(values, 95.0),
            jitter_ms=jitter,
            stalls=self.stalls, spikes=self.spikes,
            kind=self.kind, label=self.label,
            verdict=self.verdict, verdict_detail=self.verdict_detail,
            host=max(self.hosts, key=self.hosts.get) if self.hosts else "",
            link=max(self.links, key=self.links.get) if self.links else "",
            signal_pct=(int(round(sum(self.signals) / len(self.signals)))
                        if self.signals else None),
            roams=self.roams,
        )


class History:
    """Minute-by-minute history, kept on disk between runs."""

    def __init__(self, path: Optional[Path] = None, bucket_s: int = DEFAULT_BUCKET_S,
                 keep_hours: int = DEFAULT_KEEP_HOURS, load: bool = True) -> None:
        self.path = Path(path) if path is not None else (app_config_dir() / "history.json")
        self.bucket_s = max(5, int(bucket_s))
        self.keep_hours = max(1, int(keep_hours))
        maxlen = int(self.keep_hours * 3600 / self.bucket_s) + 2
        self._closed: Deque[Bucket] = deque(maxlen=maxlen)
        self._open: Optional[_OpenBucket] = None
        self._markers: List[dict] = []      # [{ts, label}] - "I changed something"
        self._dirty = False
        if load:
            self.load()

    # ------------------------------------------------------------------ input
    def add(self, sample: LatencySample) -> None:
        """Fold one sample into the minute it belongs to."""
        start = self._align(sample.ts or time.time())
        if self._open is None:
            self._open = _OpenBucket(start)
        elif start > self._open.start:
            self._roll(start)
        elif start < self._open.start:
            # A sample older than the open bucket (clock step, replayed data):
            # counting it in the current minute is better than dropping it.
            pass
        self._open.add(sample)

    def note_event(self, kind: str) -> None:
        """Record a stall or a spike against the minute it happened in."""
        if self._open is None:
            self._open = _OpenBucket(self._align(time.time()))
        if kind == "stall":
            self._open.stalls += 1
        elif kind == "spike":
            self._open.spikes += 1

    def mark(self, label: str, ts: Optional[float] = None) -> dict:
        """Record "I changed something here", so the effect can be measured.

        The tool can say the Wi-Fi is the problem. Whether moving the router
        actually helped is a different question, and nobody could answer it
        from a chart alone - a marker turns the data already being collected
        into a before-and-after.
        """
        marker = {"ts": float(ts if ts is not None else time.time()),
                  "label": str(label or "").strip()[:80]}
        self._markers.append(marker)
        self._markers.sort(key=lambda entry: entry["ts"])
        del self._markers[:-MAX_MARKERS]
        self._dirty = True
        return marker

    def markers(self, hours: Optional[float] = None) -> List[dict]:
        """Markers inside the window, oldest first."""
        if hours is None:
            return list(self._markers)
        cutoff = time.time() - float(hours) * 3600
        return [entry for entry in self._markers if entry["ts"] >= cutoff]

    def clear_markers(self) -> None:
        self._markers = []
        self._dirty = True

    def compare(self, marker_ts: float, cap_s: float = MAX_COMPARE_SPAN_S) -> Optional[dict]:
        """What changed either side of a moment, over a *fair* span.

        The span is the same on both sides on purpose. Six hours of "before"
        against five minutes of "after" would compare a whole evening with one
        quiet moment and call the difference an improvement, which is how this
        kind of feature usually lies.
        """
        rows = self.buckets()
        if not rows:
            return None
        first = rows[0].start
        last = rows[-1].start + self.bucket_s
        span = min(marker_ts - first, last - marker_ts, float(cap_s))
        if span < self.bucket_s * MIN_COMPARE_BUCKETS:
            return None       # not enough on one side to say anything honest

        before = self._window_summary(marker_ts - span, marker_ts)
        after = self._window_summary(marker_ts, marker_ts + span)
        if not before["buckets"] or not after["buckets"]:
            return None
        return {"ts": marker_ts, "span_s": span, "before": before, "after": after,
                "delta_ms": _difference(after["avg_ms"], before["avg_ms"]),
                "delta_p95_ms": _difference(after["p95_ms"], before["p95_ms"]),
                "delta_loss_pct": _difference(after["loss_pct"], before["loss_pct"])}

    def _window_summary(self, start: float, end: float) -> dict:
        """Summarise the buckets between two moments."""
        rows = [row for row in self.buckets() if start <= row.start < end]
        counted = sum(row.count for row in rows)
        answered = sum(row.ok for row in rows)
        weighted = [(row.avg_ms, row.ok) for row in rows if row.avg_ms is not None and row.ok]
        avg = None
        if weighted:
            avg = (sum(value * weight for value, weight in weighted)
                   / sum(weight for _value, weight in weighted))
        p95s = [row.p95_ms for row in rows if row.p95_ms is not None]
        return {
            "buckets": len(rows), "samples": counted,
            "avg_ms": avg, "p95_ms": percentile(p95s, 95.0),
            "loss_pct": ((counted - answered) * 100.0 / counted) if counted else 0.0,
            "stalls": sum(row.stalls for row in rows),
            "spikes": sum(row.spikes for row in rows),
        }

    def note_verdict(self, key: str, detail: str = "",
                     ts: Optional[float] = None) -> None:
        """File what an automatic check found against the minute it ran in."""
        if not key:
            return
        start = self._align(ts if ts is not None else time.time())
        if self._open is not None and start >= self._open.start:
            self._open.verdict = key
            self._open.verdict_detail = detail
            return
        # The check finished after its minute rolled over, which is normal for
        # something that takes seconds: attach it to the minute it belongs to.
        for index in range(len(self._closed) - 1, -1, -1):
            bucket = self._closed[index]
            if bucket.start == start:
                self._closed[index] = replace(bucket, verdict=key, verdict_detail=detail)
                self._dirty = True
                return
        if self._open is not None:
            self._open.verdict = key
            self._open.verdict_detail = detail

    def findings(self, hours: Optional[float] = 24.0, limit: int = 12) -> List[dict]:
        """The automatic checks that ran, newest first - "what went wrong when"."""
        found = [
            {"start": row.start, "verdict": row.verdict, "detail": row.verdict_detail,
             "stalls": row.stalls, "spikes": row.spikes}
            for row in self.buckets(hours) if row.verdict
        ]
        found.reverse()
        return found[:max(0, limit)]

    def _align(self, ts: float) -> float:
        return math.floor(float(ts) / self.bucket_s) * self.bucket_s

    def _roll(self, new_start: float) -> None:
        assert self._open is not None
        self._closed.append(self._open.close())
        self._open = _OpenBucket(new_start)
        self._dirty = True
        self._trim()

    def _trim(self) -> None:
        cutoff = time.time() - self.keep_hours * 3600
        while self._closed and self._closed[0].start < cutoff:
            self._closed.popleft()

    # ----------------------------------------------------------------- output
    def buckets(self, hours: Optional[float] = None) -> List[Bucket]:
        """Closed buckets plus the minute in progress, oldest first."""
        rows = list(self._closed)
        if self._open is not None and self._open.count:
            rows.append(self._open.close())
        if hours is not None:
            cutoff = time.time() - float(hours) * 3600
            rows = [row for row in rows if row.start >= cutoff]
        return rows

    def span_hours(self) -> float:
        rows = self.buckets()
        if not rows:
            return 0.0
        return max(0.0, (rows[-1].start + self.bucket_s - rows[0].start) / 3600.0)

    def summary(self, hours: Optional[float] = 24.0) -> dict:
        """Headline numbers over a window, computed from the buckets."""
        rows = self.buckets(hours)
        counted = sum(row.count for row in rows)
        answered = sum(row.ok for row in rows)
        weighted = [(row.avg_ms, row.ok) for row in rows if row.avg_ms is not None and row.ok]
        avg = None
        if weighted:
            total = sum(value * weight for value, weight in weighted)
            avg = total / sum(weight for _value, weight in weighted)
        highs = [row.max_ms for row in rows if row.max_ms is not None]
        lows = [row.min_ms for row in rows if row.min_ms is not None]
        p95s = [row.p95_ms for row in rows if row.p95_ms is not None]
        jitters = [row.jitter_ms for row in rows if row.jitter_ms is not None]
        return {
            "hours": hours,
            "buckets": len(rows),
            "from": rows[0].start if rows else None,
            "to": (rows[-1].start + self.bucket_s) if rows else None,
            "samples": counted,
            "ok": answered,
            "loss_pct": ((counted - answered) * 100.0 / counted) if counted else 0.0,
            "avg_ms": avg,
            "min_ms": min(lows) if lows else None,
            "max_ms": max(highs) if highs else None,
            "p95_ms": percentile(p95s, 95.0),
            "jitter_ms": (sum(jitters) / len(jitters)) if jitters else None,
            "stalls": sum(row.stalls for row in rows),
            "spikes": sum(row.spikes for row in rows),
            "label": next((row.label for row in reversed(rows) if row.label), ""),
            "kind": next((row.kind for row in reversed(rows) if row.kind), ""),
        }

    def worst_hour(self, hours: Optional[float] = 24.0) -> Optional[dict]:
        """The hour people remember: the one with the most trouble in it.

        Ranked by stalls and spikes first, because a stutter is what gets
        noticed, and by average latency only to break the tie.
        """
        rows = self.buckets(hours)
        if not rows:
            return None
        grouped: dict = {}
        for row in rows:
            key = math.floor(row.start / 3600.0) * 3600
            slot = grouped.setdefault(key, {"start": float(key), "count": 0, "ok": 0,
                                            "weighted": 0.0, "max_ms": None,
                                            "stalls": 0, "spikes": 0})
            slot["count"] += row.count
            slot["ok"] += row.ok
            if row.avg_ms is not None and row.ok:
                slot["weighted"] += row.avg_ms * row.ok
            if row.max_ms is not None:
                slot["max_ms"] = row.max_ms if slot["max_ms"] is None else max(slot["max_ms"], row.max_ms)
            slot["stalls"] += row.stalls
            slot["spikes"] += row.spikes
        for slot in grouped.values():
            slot["avg_ms"] = (slot["weighted"] / slot["ok"]) if slot["ok"] else None
            slot["loss_pct"] = ((slot["count"] - slot["ok"]) * 100.0 / slot["count"]
                                if slot["count"] else 0.0)
            slot.pop("weighted", None)
        worst = max(
            grouped.values(),
            key=lambda slot: (slot["stalls"] + slot["spikes"], slot["avg_ms"] or 0.0),
        )
        if not (worst["stalls"] or worst["spikes"] or worst["avg_ms"]):
            return None
        return worst

    # ------------------------------------------------------------- persistence
    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            LOG.warning("history file unreadable, starting fresh: %s", exc)
            return
        rows = data.get("buckets") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return
        cutoff = time.time() - self.keep_hours * 3600
        restored = []
        for row in rows:
            bucket = Bucket.from_row(row) if isinstance(row, list) else None
            if bucket is not None and bucket.start >= cutoff:
                restored.append(bucket)
        restored.sort(key=lambda bucket: bucket.start)
        self._closed.extend(restored)

        for entry in (data.get("markers") or []):
            try:
                self._markers.append({"ts": float(entry["ts"]),
                                      "label": str(entry.get("label") or "")})
            except (TypeError, ValueError, KeyError):
                continue
        self._markers.sort(key=lambda entry: entry["ts"])
        del self._markers[:-MAX_MARKERS]

    def flush(self, force: bool = False) -> bool:
        """Write the closed buckets out; returns True when it wrote."""
        if not self._dirty and not force:
            return False
        rows = [bucket.as_row() for bucket in self._closed]
        payload = json.dumps({"version": FILE_VERSION, "bucket_s": self.bucket_s,
                              "buckets": rows, "markers": self._markers},
                             ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=str(self.path.parent), delete=False, suffix=".tmp"
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_name = handle.name
            os.replace(tmp_name, self.path)
        except OSError as exc:
            LOG.warning("could not save history: %s", exc)
            return False
        self._dirty = False
        return True

    def close(self) -> None:
        """Seal the minute in progress and write everything to disk."""
        if self._open is not None and self._open.count:
            self._closed.append(self._open.close())
            self._open = None
            self._dirty = True
        self.flush()

    def clear(self) -> None:
        self._closed.clear()
        self._markers = []
        self._open = None
        self._dirty = True
        self.flush(force=True)


def percentile(values: list, pct: float) -> Optional[float]:
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


def _difference(after: Optional[float], before: Optional[float]) -> Optional[float]:
    """after - before, or None when either side has nothing to compare."""
    if after is None or before is None:
        return None
    return after - before


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 1)


def _optional_int(value) -> Optional[int]:
    """A signal percentage, or nothing when the row predates it being kept."""
    try:
        text = str(value).strip()
        return int(float(text)) if text else None
    except (TypeError, ValueError):
        return None


def _opt_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)
