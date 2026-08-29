"""An actual speed test: how fast is this line, really?

Every sample already carries the *passive* throughput - what the machine
happens to be moving right now. That answers "is something else eating my
line", and it cannot answer "how fast could this line go", because nothing
was asking it to go fast.

This does ask. Two things follow from that, and both matter more than the
number itself:

* **It saturates the line while it runs.** Latency will spike, the stream may
  stutter, and the minutes it covers are marked in the history so that spike
  is not later read as a fault.
* **It costs data.** Capped by time *and* bytes, whichever comes first, so a
  fast line stops at the byte cap rather than pulling down a gigabyte.

Where it downloads from is deliberate: the CDN already serving what you are
watching, when there is one. That measures the path that actually matters
rather than a generic test server on the other side of the country.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)

# TCP starts slow. The first stretch understates a fast line badly, so it is
# measured separately and thrown away rather than averaged in.
WARMUP_S = 1.0
DEFAULT_BUDGET_S = 10.0
DEFAULT_MAX_BYTES = 80 * 1024 * 1024
CHUNK_BYTES = 64 * 1024

# A public endpoint for the case where nothing else is being watched. Named
# here rather than buried, because it is a host this app talks to.
PUBLIC_URL = "https://speed.cloudflare.com/__down?bytes={bytes}"

# Roughly what each quality needs, for turning Mbps into a sentence.
QUALITY_TIERS = (
    (25.0, "speed.tier.4k"),
    (10.0, "speed.tier.1080p60"),
    (5.0, "speed.tier.1080p"),
    (2.5, "speed.tier.720p"),
    (0.0, "speed.tier.low"),
)


@dataclass(frozen=True)
class SpeedResult:
    """What one download achieved, and what it cost to find out."""

    mbps: Optional[float] = None
    bytes: int = 0
    seconds: float = 0.0
    host: str = ""
    source: str = "public"          # "stream" when it used the CDN in use
    ramp_mbps: Optional[float] = None   # including slow start, for comparison
    warmed: bool = True             # False when it ended before the ramp did
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.mbps is not None and self.error is None

    def as_dict(self) -> dict:
        return {"mbps": self.mbps, "bytes": self.bytes, "seconds": self.seconds,
                "host": self.host, "source": self.source, "warmed": self.warmed,
                "error": self.error}


def tier_key(mbps: Optional[float]) -> str:
    """The highest quality this speed comfortably carries."""
    if mbps is None:
        return "speed.tier.low"
    for threshold, key in QUALITY_TIERS:
        if mbps >= threshold:
            return key
    return "speed.tier.low"


def measure_download(session, url: str, *, budget_s: float = DEFAULT_BUDGET_S,
                     max_bytes: int = DEFAULT_MAX_BYTES, headers: Optional[dict] = None,
                     source: str = "public",
                     on_progress: Optional[Callable[[float, int], None]] = None
                     ) -> SpeedResult:
    """Download as fast as the line allows, for a bounded time and size.

    The rate is taken from the stretch *after* the warm-up, because TCP slow
    start would otherwise make a fast connection look mediocre. Both figures
    are reported so the difference is visible rather than hidden.
    """
    host = urlparse(url).hostname or ""
    if not url:
        return SpeedResult(source=source, error="no-url")

    started = time.perf_counter()
    total = 0
    warm_start: Optional[float] = None
    warm_bytes = 0

    try:
        response = session.get(url, headers=headers or {}, timeout=budget_s + 5.0,
                               stream=True)
    except Exception as exc:                      # noqa: BLE001 - report anything
        return SpeedResult(host=host, source=source, error=str(exc)[:160])

    try:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
            if not chunk:
                continue
            now = time.perf_counter()
            elapsed = now - started
            total += len(chunk)

            if warm_start is None and elapsed >= WARMUP_S:
                warm_start, warm_bytes = now, 0     # the clock that counts
            elif warm_start is not None:
                warm_bytes += len(chunk)

            if on_progress is not None:
                on_progress(elapsed, total)
            if elapsed >= budget_s or total >= max_bytes:
                break
    except Exception as exc:                      # noqa: BLE001
        if total <= 0:
            return SpeedResult(host=host, source=source, error=str(exc)[:160])
        LOG.debug("speed test ended early: %s", exc)
    finally:
        response.close()

    total_s = max(1e-6, time.perf_counter() - started)
    if total <= 0:
        return SpeedResult(host=host, source=source, seconds=total_s, error="no-data")

    ramp_mbps = (total * 8) / total_s / 1_000_000.0
    if warm_start is not None and warm_bytes > 0:
        warm_s = max(1e-6, time.perf_counter() - warm_start)
        mbps = (warm_bytes * 8) / warm_s / 1_000_000.0
        warmed = True
    else:
        # It finished before slow start was over - a small file or a slow line.
        # The whole-run figure is all there is, and it is honest about being it.
        mbps, warmed = ramp_mbps, False

    return SpeedResult(mbps=mbps, bytes=total, seconds=total_s, host=host,
                       source=source, ramp_mbps=ramp_mbps, warmed=warmed)


def public_url(max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    return PUBLIC_URL.format(bytes=int(max_bytes))
