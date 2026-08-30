"""Turning "it's always laggy" into something that can be checked.

The app could already answer *how is it right now* and *why did that stall
happen*. It could not answer "always", which is the word people actually use -
and "always" is a claim about a pattern, not about a moment.

Two questions get answered here, both out of history that is already recorded:

**Which machine was I on?** Every minute now remembers the CDN edge that served
it, so the good minutes and the bad ones can be grouped by edge. That is the
difference between "sometimes it stutters" and "it stutters on that node, and
you are on it half the time" - the second is actionable and the first is not.

**When is it bad?** Grouping by hour of the day and by weekday turns a wall of
minutes into "weekday evenings" or "no pattern at all". Saying there is no
pattern is a real answer here, not a failure: it rules out congestion and
points at something local.

Everything refuses to conclude below a minimum sample count. A node you were on
for four minutes is not evidence about that node, and an hour with two samples
in it is not a bad hour.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


# Below this an edge has not been observed enough to compare with another.
MIN_BUCKETS_PER_EDGE = 10
# An hour of the week needs this many minutes recorded before it is ranked.
MIN_BUCKETS_PER_HOUR = 15
# Two edges within this are the same as far as anyone watching can tell.
EDGE_DIFFERENCE_MS = 15.0
# A period must be this much worse than the overall average to be "the bad time".
PERIOD_DIFFERENCE_MS = 20.0


@dataclass
class EdgeStats:
    """How one CDN edge actually performed, and how much you were on it."""

    host: str = ""
    buckets: int = 0
    samples: int = 0
    ok: int = 0
    avg_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    stalls: int = 0
    share_pct: float = 0.0          # of the time covered by the comparison

    @property
    def loss_pct(self) -> float:
        if not self.samples:
            return 0.0
        return (self.samples - self.ok) * 100.0 / self.samples

    @property
    def comparable(self) -> bool:
        return self.buckets >= MIN_BUCKETS_PER_EDGE

    def as_dict(self) -> dict:
        return {"host": self.host, "buckets": self.buckets, "avg_ms": self.avg_ms,
                "p95_ms": self.p95_ms, "loss_pct": round(self.loss_pct, 1),
                "stalls": self.stalls, "share_pct": round(self.share_pct, 1)}


def by_edge(buckets: Sequence) -> List[EdgeStats]:
    """Group recorded minutes by the edge that served them, worst last.

    Only minutes that recorded an edge take part; history written before that
    was kept simply has nothing to say here and is left out rather than
    lumped into an "unknown" bucket that would dilute the real ones.
    """
    grouped: dict = {}
    for bucket in buckets or ():
        host = getattr(bucket, "host", "") or ""
        if not host or bucket.avg_ms is None:
            continue
        grouped.setdefault(host, []).append(bucket)

    total = sum(len(rows) for rows in grouped.values())
    out = []
    for host, rows in grouped.items():
        averages = [row.avg_ms for row in rows if row.avg_ms is not None]
        p95s = [row.p95_ms for row in rows if row.p95_ms is not None]
        samples = sum(row.count for row in rows)
        out.append(EdgeStats(
            host=host,
            buckets=len(rows),
            samples=samples,
            ok=sum(row.ok for row in rows),
            avg_ms=(sum(averages) / len(averages)) if averages else None,
            p95_ms=(sum(p95s) / len(p95s)) if p95s else None,
            stalls=sum(row.stalls for row in rows),
            share_pct=(len(rows) * 100.0 / total) if total else 0.0,
        ))
    out.sort(key=lambda stats: (stats.avg_ms is None, stats.avg_ms or 0.0))
    return out


@dataclass
class EdgeVerdict:
    """Whether the edge you get actually explains anything."""

    best: Optional[EdgeStats] = None
    worst: Optional[EdgeStats] = None
    difference_ms: Optional[float] = None
    key: str = "edge.none"          # what to tell the reader

    @property
    def matters(self) -> bool:
        return self.key == "edge.differs"


def edge_verdict(stats: Sequence) -> EdgeVerdict:
    """Say whether which edge you were given made a difference worth acting on."""
    usable = [item for item in stats or () if item.comparable and item.avg_ms is not None]
    if not usable:
        return EdgeVerdict(key="edge.not_enough")
    if len(usable) == 1:
        return EdgeVerdict(best=usable[0], key="edge.only_one")

    best = usable[0]
    # Not the slowest edge - the one costing the most *overall*. An edge that
    # is dreadful for four minutes matters less than a mediocre one you are
    # parked on for half the evening, and telling someone to act on the first
    # sends them after the smaller problem.
    def cost(stats):
        return ((stats.avg_ms or 0.0) - (best.avg_ms or 0.0)) * stats.share_pct / 100.0

    worst = max(usable, key=cost)
    difference = (worst.avg_ms or 0.0) - (best.avg_ms or 0.0)
    if worst is best or difference < EDGE_DIFFERENCE_MS:
        return EdgeVerdict(best=best, worst=worst, difference_ms=difference,
                           key="edge.same")
    return EdgeVerdict(best=best, worst=worst, difference_ms=difference,
                       key="edge.differs")


@dataclass
class Period:
    """One hour of the week, and how it went."""

    weekday: int = 0                # 0 = Monday, matching time.struct_tm
    hour: int = 0
    buckets: int = 0
    avg_ms: Optional[float] = None
    stalls: int = 0

    @property
    def label(self) -> str:
        return f"{self.weekday}:{self.hour:02d}"


@dataclass
class PatternReport:
    """When it is bad, if there is a when at all."""

    overall_ms: Optional[float] = None
    periods: List[Period] = field(default_factory=list)
    worst: Optional[Period] = None
    worst_hours: List[int] = field(default_factory=list)
    days_covered: float = 0.0
    key: str = "pattern.none"

    @property
    def has_pattern(self) -> bool:
        return self.key == "pattern.found"


def by_period(buckets: Sequence, now: Optional[float] = None) -> PatternReport:
    """Group minutes by hour of the week and find the bad stretch, if any.

    "No pattern" is a real answer: it rules out the whole family of causes that
    follow a clock - peak-hour congestion, a scheduled backup, a housemate's
    routine - and points somewhere else instead.
    """
    rows = [row for row in buckets or () if row.avg_ms is not None]
    if not rows:
        return PatternReport(key="pattern.no_data")

    grouped: dict = {}
    for row in rows:
        stamp = time.localtime(row.start)
        grouped.setdefault((stamp.tm_wday, stamp.tm_hour), []).append(row)

    periods = []
    for (weekday, hour), items in grouped.items():
        averages = [item.avg_ms for item in items if item.avg_ms is not None]
        periods.append(Period(
            weekday=weekday, hour=hour, buckets=len(items),
            avg_ms=(sum(averages) / len(averages)) if averages else None,
            stalls=sum(item.stalls for item in items),
        ))
    periods.sort(key=lambda period: (period.weekday, period.hour))

    all_averages = [row.avg_ms for row in rows if row.avg_ms is not None]
    overall = sum(all_averages) / len(all_averages)
    span_s = max(row.start for row in rows) - min(row.start for row in rows)
    days = span_s / 86400.0

    ranked = [p for p in periods if p.buckets >= MIN_BUCKETS_PER_HOUR and p.avg_ms is not None]
    ranked.sort(key=lambda period: period.avg_ms or 0.0, reverse=True)
    if not ranked:
        return PatternReport(overall_ms=overall, periods=periods, days_covered=days,
                             key="pattern.not_enough")

    worst = ranked[0]
    if (worst.avg_ms or 0.0) - overall < PERIOD_DIFFERENCE_MS:
        return PatternReport(overall_ms=overall, periods=periods, days_covered=days,
                             key="pattern.none")

    # Every hour of the day that is meaningfully worse, so "21:00-23:00" can be
    # reported rather than just the single worst hour inside it.
    bad_hours = sorted({period.hour for period in ranked
                        if (period.avg_ms or 0.0) - overall >= PERIOD_DIFFERENCE_MS})
    return PatternReport(overall_ms=overall, periods=periods, worst=worst,
                         worst_hours=bad_hours, days_covered=days,
                         key="pattern.found")


def hour_ranges(hours: Sequence) -> List[tuple]:
    """[21, 22, 23, 9] -> [(21, 23), (9, 9)], so it reads as a time range."""
    out: List[tuple] = []
    for hour in sorted(set(int(h) for h in hours or ())):
        if out and hour == out[-1][1] + 1:
            out[-1] = (out[-1][0], hour)
        else:
            out.append((hour, hour))
    return out
