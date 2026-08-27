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
os.environ.setdefault("BILI_LATENCY_CONFIG_DIR", tempfile.mkdtemp(prefix="bili-shots-"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtGui import QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from bili_latency.config import Config  # noqa: E402
from bili_latency.i18n import set_language  # noqa: E402
from bili_latency.models import LatencySample, RollingStats  # noqa: E402
from bili_latency.probes.display import DisplayProbe  # noqa: E402
from bili_latency.ui.icons import value_pixmap  # noqa: E402
from bili_latency.ui.overlay import OverlayWindow  # noqa: E402
from bili_latency.ui.settings import SettingsDialog  # noqa: E402

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


def shoot_overlay(name: str, config: Config, sample, stats) -> None:
    window = OverlayWindow(config, DisplayProbe())
    window.show()
    window.set_room_label("房间 21452505")
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
