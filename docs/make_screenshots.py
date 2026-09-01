#!/usr/bin/env python3
"""Regenerate the screenshots used by README.md.

    python docs/make_screenshots.py

Runs headless (offscreen Qt), so it works over SSH and in CI.
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LAGSCOPE_CONFIG_DIR", tempfile.mkdtemp(prefix="lagscope-shots-"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtGui import QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lagscope.config import Config  # noqa: E402
from lagscope.history import History  # noqa: E402
from lagscope.i18n import set_language  # noqa: E402
from lagscope.models import (  # noqa: E402
    KIND_APP, KIND_TARGET, KIND_VIDEO, ExtraResult, LatencySample, RollingStats,
)
from lagscope.probes.display import DisplayProbe  # noqa: E402
from lagscope.ui.icons import value_pixmap  # noqa: E402
from lagscope.ui.history_window import HistoryWindow  # noqa: E402
from lagscope.ui.overlay import OverlayWindow  # noqa: E402
from lagscope.ui.settings import SettingsDialog  # noqa: E402
from lagscope.ui.wizard import SetupWizard  # noqa: E402

OUT = ROOT / "docs" / "images"


def demo_stats() -> tuple[LatencySample, RollingStats]:
    stats = RollingStats(120)
    sample = LatencySample()
    for index in range(60):
        total = 2400 + math.sin(index / 4.0) * 520 + (index % 7) * 15
        sample = LatencySample(
            network_ms=38 + (index % 5) * 2,
            stream_ms=total - 33,
            display_ms=33.2,
            total_ms=total,
            ok=True,
            estimated=False,
            method="hls-pdt",
            host="cn-hbyc-ct-01.bilivideo.com",
        )
        stats.append(sample)
    return sample, stats


def video_stats() -> tuple[LatencySample, RollingStats]:
    stats = RollingStats(120)
    sample = LatencySample()
    for index in range(60):
        total = 780 + math.sin(index / 5.0) * 180 + (index % 5) * 12
        sample = LatencySample(
            network_ms=34 + (index % 4) * 3,
            stream_ms=total - 33,
            display_ms=33.2,
            total_ms=total,
            ok=True,
            kind=KIND_VIDEO,
            method="video-startup",
            host="upos-sz-mirrorcos.bilivideo.com",
            throughput_mbps=42.6,
            required_mbps=3.1,
        )
        stats.append(sample)
    return sample, stats


def app_stats() -> tuple[LatencySample, RollingStats]:
    stats = RollingStats(120)
    sample = LatencySample()
    for index in range(60):
        total = 42 + math.sin(index / 5.0) * 9 + (index % 4)
        sample = LatencySample(
            network_ms=total - 33.2,
            display_ms=33.2,
            total_ms=total,
            ok=True,
            kind=KIND_APP,
            method="tcp",
            host="93.184.216.34:443",
            title="ValorantGame.exe",
            connections=6,
            up_mbps=1.9,
            down_mbps=48.3,
        )
        stats.append(sample)
    return sample, stats


DEMO_EXTRAS = [
    ExtraResult(key="a", label="路由器", kind=KIND_TARGET, ident="192.168.1.1",
                rtt_ms=2.1, ok=True),
    ExtraResult(key="b", label="DNS 8.8.8.8", kind=KIND_TARGET, ident="8.8.8.8",
                rtt_ms=28.0, ok=True),
    ExtraResult(key="c", label="Discord 語音", kind=KIND_APP, ident="Discord.exe",
                rtt_ms=180.0, ok=True),
]


def _analysis(history, hours) -> dict:
    """The same edge/pattern/action analysis the app builds for this window."""
    from lagscope.actions import suggest
    from lagscope.i18n import tr
    from lagscope.patterns import by_edge, by_period, edge_verdict, hour_ranges
    from lagscope.probes.cdninfo import describe

    buckets = history.buckets(hours)
    edges = by_edge(buckets)
    verdict = edge_verdict(edges)
    if verdict.key == "edge.differs" and verdict.best and verdict.worst:
        note = tr("edge.differs", worst=verdict.worst.host, best=verdict.best.host,
                  diff=f"{verdict.difference_ms:.0f}",
                  share=f"{verdict.worst.share_pct:.0f}")
    else:
        note = tr(verdict.key)

    pattern = by_period(buckets)
    if pattern.has_pattern and pattern.worst:
        when = "、".join(tr("pattern.range", start=f"{a:02d}", end=f"{b:02d}")
                         for a, b in hour_ranges(pattern.worst_hours))
        pattern_note = tr("pattern.found", when=when,
                          bad=f"{pattern.worst.avg_ms:.0f}",
                          overall=f"{pattern.overall_ms:.0f}")
    else:
        pattern_note = tr(pattern.key)

    return {
        "edges": edges, "edge_note": note, "pattern_note": pattern_note,
        "actions": suggest(edge_verdict=verdict, pattern=pattern,
                           verdict_key="verdict.isp",
                           peer_hosts=[e.host for e in edges
                                       if describe(e.host).is_peer]),
    }


def demo_history() -> History:
    """Six hours with a quiet stretch, a sleeping machine and one bad evening."""
    history = History(load=False)
    now = math.floor(time.time() / 60) * 60
    random.seed(7)
    for minute in range(6 * 60):
        ts = now - (6 * 60 - minute) * 60
        if 150 < minute < 170:                  # the machine was asleep
            continue
        base = 120 + 30 * math.sin(minute / 40)
        host = "upos-sz-mirrorhw.bilivideo.com"
        if 300 < minute < 330:                  # the evening that went wrong
            base = 420 + random.random() * 260
        if minute > 240:                        # and it went wrong on one edge
            host = "cn-hbyc-ct-01.bilivideo.com"
        for step in range(3):
            history.add(LatencySample(ts=ts + step * 20, ok=True, title="直播間 21452505",
                                      host=host, total_ms=base + random.random() * 40))
        if 305 < minute < 315 and minute % 3 == 0:
            history.note_event("stall")
        if 300 < minute < 330 and minute % 7 == 0:
            history.note_event("spike")
    return history


def shoot_overlay(name: str, config: Config, sample, stats, label="直播間 21452505",
                  extras=()) -> None:
    window = OverlayWindow(config, DisplayProbe())
    window.show()
    window.set_extras(list(extras))
    window.set_room_label(label)
    window.update_sample(sample, stats)
    QApplication.processEvents()
    window.grab().save(str(OUT / name), "PNG")
    window.close()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    # Set before anything is drawn: this used to be called at the end, where
    # it changed nothing, and every screenshot came out in the wrong language.
    set_language("zh_TW")
    OUT.mkdir(parents=True, exist_ok=True)
    sample, stats = demo_stats()

    config = Config()
    shoot_overlay("overlay-dark.png", config, sample, stats)

    light = Config()
    light.overlay.theme = "light"
    shoot_overlay("overlay-light.png", light, sample, stats)

    compact = Config()
    compact.overlay.theme = "pink"
    compact.overlay.compact = True
    compact.overlay.scale = 1.6
    shoot_overlay("overlay-compact.png", compact, sample, stats)

    video_sample, video_series = video_stats()
    shoot_overlay("overlay-video.png", Config(), video_sample, video_series,
                  label="影片 【4K】測試影片標題 P2")

    app_sample, app_series = app_stats()
    app_config = Config()
    app_config.thresholds.good_ms = 60
    app_config.thresholds.warn_ms = 150
    shoot_overlay("overlay-app.png", app_config, app_sample, app_series,
                  label="應用程式 ValorantGame.exe", extras=DEMO_EXTRAS)

    history_config = Config()
    history_config.thresholds.good_ms = 200
    history_config.thresholds.warn_ms = 500
    history = demo_history()
    window = HistoryWindow(history_config, history)
    window.set_analysis_provider(lambda hours: _analysis(history, hours))
    window.resize(900, 660)
    window.show()
    QApplication.processEvents()
    window.grab().save(str(OUT / "history.png"), "PNG")
    window.close()

    wizard = SetupWizard(Config())
    wizard.show()
    QApplication.processEvents()
    wizard.grab().save(str(OUT / "wizard.png"), "PNG")
    wizard.close()

    dialog = SettingsDialog(Config())
    dialog.room_edit.setText("https://live.bilibili.com/21452505")
    dialog.show()
    QApplication.processEvents()
    dialog.grab().save(str(OUT / "settings.png"), "PNG")
    dialog.close()

    strip = QPixmap(4 * 96, 96)
    strip.fill()
    painter = QPainter(strip)
    for index, (text, color) in enumerate(
        [("82", "#3fd07f"), ("480", "#3fd07f"), ("2.4s", "#f6c445"), ("12s", "#ff5d5d")]
    ):
        painter.drawPixmap(index * 96, 0, value_pixmap(text, color, 96))
    painter.end()
    strip.save(str(OUT / "tray-icons.png"), "PNG")

    print(f"screenshots written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
