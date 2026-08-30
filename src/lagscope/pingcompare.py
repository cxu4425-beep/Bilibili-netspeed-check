"""Why this app's latency does not match ``ping``, answered with measurements.

Someone comparing the number here against ``ping`` in a terminal and finding a
forty millisecond gap is doing exactly the right thing, and deserves better
than being told the tool is right. There are four ordinary reasons for a gap,
and they are not equally likely:

1. **The two are not measuring the same machine.** This app measures the CDN
   edge actually serving the stream; a hand-typed ``ping bilibili.com`` hits
   whatever the front door resolves to, which can be a different city. This is
   far and away the most common cause and the easiest to overlook.
2. **ICMP and TCP are different paths.** Routers and edges routinely handle
   ICMP at a lower priority, rate limit it, or answer it from a box in front of
   the one that terminates TCP. Either can come out ahead.
3. **The name lookup used to be counted in.** It no longer is; it is reported
   on its own line so the split is visible rather than asserted.
4. **Resolution.** Windows ``ping`` rounds to whole milliseconds and people
   read the best of four packets, against a single sample here.

So this runs both, against the *same resolved address*, several times, and
prints them side by side. Then it says which of the four the numbers point at,
rather than leaving the reader to guess.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import APP_NAME, __version__
from .probes.cdninfo import describe
from .probes.network import connect_timing, icmp_ping_ms
from .textfmt import pad, width

DEFAULT_ROUNDS = 5
# Below this the two agree as well as either can be measured; a gap smaller
# than the resolution of the coarser tool is not a discrepancy worth a story.
NOISE_MS = 5.0
# ICMP handled by a different box, or deprioritised, shows up as a wide gap
# in either direction rather than a small consistent offset.
WIDE_GAP_MS = 15.0


@dataclass
class PingComparison:
    """Both measurements of one host, and what the difference means."""

    host: str = ""
    address: str = ""
    port: int = 443
    dns_ms: Optional[float] = None
    tcp_samples: List[float] = field(default_factory=list)
    icmp_samples: List[float] = field(default_factory=list)
    error: str = ""

    @staticmethod
    def _best(samples):
        return min(samples) if samples else None

    @staticmethod
    def _median(samples):
        return statistics.median(samples) if samples else None

    @property
    def tcp_best(self):
        return self._best(self.tcp_samples)

    @property
    def icmp_best(self):
        return self._best(self.icmp_samples)

    @property
    def gap_ms(self):
        """TCP minus ICMP, at their best - positive means TCP looks slower."""
        if self.tcp_best is None or self.icmp_best is None:
            return None
        return self.tcp_best - self.icmp_best

    @property
    def verdict_key(self) -> str:
        """Which of the four explanations these numbers actually support."""
        if self.tcp_best is None:
            return "pingcmp.verdict.no_tcp"
        if self.icmp_best is None:
            return "pingcmp.verdict.no_icmp"
        gap = abs(self.gap_ms or 0.0)
        if gap <= NOISE_MS:
            return "pingcmp.verdict.agree"
        if gap >= WIDE_GAP_MS:
            return "pingcmp.verdict.wide"
        return "pingcmp.verdict.small"


def compare(host: str, port: int = 443, rounds: int = DEFAULT_ROUNDS,
            timeout_s: float = 4.0) -> PingComparison:
    """Time ICMP and TCP against the same address, several times each."""
    if not host:
        return PingComparison(error="no-host")

    first = connect_timing(host, port, timeout_s)
    if not first.ok and not first.address:
        return PingComparison(host=host, port=port, dns_ms=first.dns_ms,
                              error=first.error or "unreachable")

    address = first.address or host
    result = PingComparison(host=host, address=address, port=port,
                            dns_ms=first.dns_ms)
    if first.rtt_ms is not None:
        result.tcp_samples.append(first.rtt_ms)

    for index in range(max(0, rounds - 1)):
        # Against the resolved address, so the lookup is not re-billed to the
        # handshake and both tools are aimed at the same machine.
        timing = connect_timing(address, port, timeout_s)
        if timing.rtt_ms is not None:
            result.tcp_samples.append(timing.rtt_ms)
        if index < rounds - 1:
            time.sleep(0.05)

    for _ in range(rounds):
        sample = icmp_ping_ms(address, timeout_s)
        if sample is not None:
            result.icmp_samples.append(sample)

    return result


def format_report(result: PingComparison) -> str:
    """The comparison as text, in the shape ``--selftest`` already uses."""
    from .i18n import tr
    from .probes.cdninfo import summary

    lines = [
        f"{APP_NAME} {__version__} - {tr('pingcmp.title')}",
        time.strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]
    if result.error and not result.tcp_samples:
        lines.append(f"{tr('pingcmp.host')}: {result.host}")
        lines.append(f"{tr('pingcmp.failed')}: {result.error}")
        return "\n".join(lines)

    info = describe(result.host)
    lines.append(f"{tr('pingcmp.host')}: {result.host}")
    lines.append(f"{tr('pingcmp.address')}: {result.address}:{result.port}")
    if info.operator_key or info.located:
        lines.append(f"{tr('pingcmp.server')}: {summary(result.host)}")
    if info.is_peer:
        lines.append(f"        !! {tr('cdn.peer.warn')}")
    lines.append("")

    def row(label, samples):
        if not samples:
            return f"  {pad(label, 34)} {tr('pingcmp.none')}"
        best = min(samples)
        median = statistics.median(samples)
        return (f"  {pad(label, 34)} {tr('pingcmp.best')} {best:6.1f} ms   "
                f"{tr('pingcmp.median')} {median:6.1f} ms")

    lines.append(row(tr("pingcmp.row.tcp"), result.tcp_samples))
    lines.append(row(tr("pingcmp.row.icmp"), result.icmp_samples))
    if result.dns_ms is not None:
        # Padded past the "best" label so the numbers sit in one column.
        dns_label = pad(tr("pingcmp.row.dns"), 34) + " " * (width(tr("pingcmp.best")) + 1)
        lines.append(f"  {dns_label}{result.dns_ms:6.1f} ms   "
                     f"{tr('pingcmp.dns_note')}")
    lines.append("")

    if result.gap_ms is not None:
        lines.append(f"{tr('pingcmp.gap')}: {result.gap_ms:+.1f} ms")
    lines.append(tr(result.verdict_key))
    lines.append("")
    lines.append(tr("pingcmp.footer"))
    return "\n".join(lines)
