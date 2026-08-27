"""Status bar / system tray icon.

The icon itself is redrawn with the current latency, so the number is readable
without opening anything - that is the "keep it in the status bar" mode. The
overlay is the "keep it on the Bilibili window" mode; both can run at once.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from .. import APP_NAME
from ..config import Config
from ..i18n import tr
from ..models import KIND_VIDEO, LatencySample
from .icons import app_icon, value_icon
from .theme import (
    color_for_level, format_mbps, format_ms, format_ms_short, level_for, palette_for,
)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(app_icon(), parent)
        self._config = config
        self._last_key: tuple = ()
        self.setToolTip(APP_NAME)

    def apply_config(self, config: Config) -> None:
        self._config = config
        self._last_key = ()
        if not config.tray.show_value_in_icon:
            self.setIcon(app_icon())

    def set_menu(self, menu: QMenu) -> None:
        self.setContextMenu(menu)

    def update_sample(self, sample: Optional[LatencySample], status_text: str) -> None:
        palette = palette_for(self._config.overlay.theme)
        value = sample.total_ms if (sample and sample.ok) else None
        level = level_for(value, self._config.thresholds.good_ms, self._config.thresholds.warn_ms)
        color = color_for_level(palette, level)

        if self._config.tray.show_value_in_icon:
            text = format_ms_short(value)
            key = (text, color)
            if key != self._last_key:
                self._last_key = key
                self.setIcon(value_icon(text, color))

        is_video = sample is not None and sample.kind == KIND_VIDEO
        fields = {
            "title": sample.title if (sample and sample.title) else APP_NAME,
            "total": format_ms(value),
            "network": format_ms(sample.network_ms if sample else None),
            "stream": format_ms(sample.stream_ms if sample else None),
            "display": format_ms(sample.display_ms if sample else None),
            "status": status_text,
        }
        if is_video:
            fields["speed"] = format_mbps(sample.throughput_mbps)
        self.setToolTip(tr("tray.tooltip_video" if is_video else "tray.tooltip", **fields))
