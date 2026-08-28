#!/usr/bin/env python3
"""Regenerate the screenshots used by README.md.

    python docs/make_screenshots.py

Runs headless (offscreen Qt), so it works over SSH and in CI.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LAGSCOPE_CONFIG_DIR", tempfile.mkdtemp(prefix="lagscope-shots-"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtGui import QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lagscope.config import Config  # noqa: E402
from lagscope.i18n import set_language  # noqa: E402
from lagscope.models import (  # noqa: E402
    KIND_APP, KIND_TARGET, KIND_VIDEO, ExtraResult, LatencySample, RollingStats,
)
from lagscope.probes.display import DisplayProbe  # noqa: E402
from lagscope.ui.icons import value_pixmap  # noqa: E402
from lagscope.ui.overlay import OverlayWindow  # noqa: E402
from lagscope.ui.settings import SettingsDialog  # noqa: E402

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
    ExtraResult(key="c", label="Discord 语音", kind=KIND_APP, ident="Discord.exe",
                rtt_ms=180.0, ok=True),
]


def shoot_overlay(name: str, config: Config, sample, stats, label="房间 21452505",
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
                  label="视频 【4K】测试影片标题 P2")

    app_sample, app_series = app_stats()
    app_config = Config()
    app_config.thresholds.good_ms = 60
    app_config.thresholds.warn_ms = 150
    shoot_overlay("overlay-app.png", app_config, app_sample, app_series,
                  label="应用 ValorantGame.exe", extras=DEMO_EXTRAS)

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
    set_language("zh_CN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
