"""The chart that answers "when was it bad?".

The overlay shows the last few minutes, which is no help the morning after.
This window plots every minute that has been recorded: the average as a line,
the best-to-worst spread of each minute as a band around it, and a tick on the
floor wherever a stall or a spike happened. Two days fit on one screen and the
evening that went wrong is visible without reading a single number.

The same data leaves here as a report, so what you looked at is exactly what
the helpdesk receives.
"""

from __future__ import annotations

import time
from typing import List, Optional, Sequence

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..config import Config
from ..history import Bucket, History
from ..i18n import tr
from ..report import grid_values, nice_ceiling, worst_hour_line
from .icons import app_icon
from .theme import Palette, format_ms, palette_for

RANGES = (("history.range.1h", 1.0), ("history.range.6h", 6.0),
          ("history.range.24h", 24.0), ("history.range.all", None))


class HistoryChart(QWidget):
    """Minute buckets drawn as a band with an average line through it."""

    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._buckets: List[Bucket] = []
        self._bucket_s = 60.0
        self._markers: List[dict] = []
        self.setMinimumHeight(220)

    def set_config(self, config: Config) -> None:
        self._config = config
        self.update()

    def set_data(self, buckets: Sequence[Bucket], bucket_s: float,
                 markers: Sequence = ()) -> None:
        self._buckets = list(buckets)
        self._bucket_s = max(1.0, float(bucket_s))
        self._markers = list(markers)
        self.update()

    def _palette(self) -> Palette:
        return palette_for(self._config.overlay.theme)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        palette = self._palette()
        painter.fillRect(self.rect(), QColor(palette.background))

        rows = [row for row in self._buckets if row.avg_ms is not None]
        if not rows:
            painter.setPen(QPen(QColor(palette.muted)))
            painter.drawText(self.rect(), Qt.AlignCenter, tr("history.empty"))
            painter.end()
            return

        pad_left, pad_right, pad_top, pad_bottom = 62.0, 12.0, 12.0, 22.0
        plot = QRectF(pad_left, pad_top,
                      max(10.0, self.width() - pad_left - pad_right),
                      max(10.0, self.height() - pad_top - pad_bottom))

        first = rows[0].start
        last = rows[-1].start + self._bucket_s
        span = max(self._bucket_s, last - first)
        # A round top means round gridline labels, which is the whole point of them.
        top = nice_ceiling(max(row.max_ms or row.avg_ms or 0.0 for row in rows) * 1.02)

        def x_of(ts: float) -> float:
            return plot.left() + (ts - first) / span * plot.width()

        def y_of(value: float) -> float:
            clamped = max(0.0, min(top, value))
            return plot.bottom() - (clamped / top) * plot.height()

        self._paint_grid(painter, palette, plot, top)
        self._paint_hours(painter, palette, plot, first, last, x_of)

        band = QColor(palette.accent)
        band.setAlpha(60)
        for run in _runs(rows, self._bucket_s):
            path = QPainterPath()
            path.moveTo(x_of(run[0].start + self._bucket_s / 2), y_of(run[0].max_ms or run[0].avg_ms))
            for row in run[1:]:
                path.lineTo(x_of(row.start + self._bucket_s / 2), y_of(row.max_ms or row.avg_ms))
            for row in reversed(run):
                path.lineTo(x_of(row.start + self._bucket_s / 2), y_of(row.min_ms or row.avg_ms))
            path.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.setBrush(band)
            painter.drawPath(path)

            line = QPainterPath()
            line.moveTo(x_of(run[0].start + self._bucket_s / 2), y_of(run[0].avg_ms))
            for row in run[1:]:
                line.lineTo(x_of(row.start + self._bucket_s / 2), y_of(row.avg_ms))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(palette.accent), 1.6))
            painter.drawPath(line)

        for row in self._buckets:
            if not (row.stalls or row.spikes):
                continue
            colour = QColor(palette.bad if row.stalls else palette.warn)
            x = x_of(row.start + self._bucket_s / 2)
            painter.fillRect(QRectF(x - 1.5, plot.bottom() - 7.0, 3.0, 7.0), colour)

        # "I changed something here" - the line the before/after is measured from.
        for marker in self._markers:
            stamp = float(marker.get("ts", 0.0))
            if not (first <= stamp <= last):
                continue
            x = x_of(stamp)
            painter.setPen(QPen(QColor(palette.foreground), 1.0, Qt.DashLine))
            painter.drawLine(x, plot.top(), x, plot.bottom())
            label = str(marker.get("label") or "")
            if label:
                painter.setFont(QFont(self.font().family(), 8))
                metrics = QFontMetrics(painter.font())
                text = metrics.elidedText(label, Qt.ElideRight, 140)
                painter.drawText(QRectF(x + 3, plot.top() + 2, 140, 16),
                                 Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.end()

    def _paint_grid(self, painter: QPainter, palette: Palette, plot: QRectF, top: float) -> None:
        painter.setFont(QFont(self.font().family(), 8))
        for value in grid_values(top):
            y = plot.bottom() - (value / top) * plot.height()
            painter.setPen(QPen(QColor(palette.border), 1.0, Qt.DotLine))
            painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(QPen(QColor(palette.muted)))
            painter.drawText(QRectF(0, y - 8, plot.left() - 6, 16),
                             Qt.AlignRight | Qt.AlignVCenter, format_ms(value))

    def _paint_hours(self, painter: QPainter, palette: Palette, plot: QRectF,
                     first: float, last: float, x_of) -> None:
        metrics = QFontMetrics(painter.font())
        step_h = 1
        span_h = (last - first) / 3600.0
        for candidate in (1, 2, 3, 6, 12, 24):
            step_h = candidate
            if span_h / candidate <= 10:
                break
        tick = (int(first) // 3600 + 1) * 3600
        previous_right = plot.left() - 10
        while tick <= last:
            if int(time.strftime("%H", time.localtime(tick))) % step_h == 0:
                x = x_of(tick)
                painter.setPen(QPen(QColor(palette.border), 1.0))
                painter.drawLine(x, plot.top(), x, plot.bottom())
                label = time.strftime("%H:%M", time.localtime(tick))
                width = metrics.horizontalAdvance(label) + 8
                if x - width / 2 > previous_right:
                    painter.setPen(QPen(QColor(palette.muted)))
                    painter.drawText(QRectF(x - width / 2, plot.bottom() + 2, width, 18),
                                     Qt.AlignCenter, label)
                    previous_right = x + width / 2
            tick += 3600


class HistoryWindow(QDialog):
    """Chart, headline numbers, and the two buttons that get it to someone else."""

    exportRequested = Signal()
    copyRequested = Signal()
    markRequested = Signal()

    def __init__(self, config: Config, history: History,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._history = history
        self._hours: Optional[float] = 24.0

        self.setWindowTitle(tr("history.title"))
        self.setWindowIcon(app_icon())
        self.resize(880, 460)

        layout = QVBoxLayout(self)

        self._range_row = QHBoxLayout()
        self._range_buttons = []
        for key, hours in RANGES:
            button = QPushButton(tr(key), self)
            button.setCheckable(True)
            button.setChecked(hours == self._hours)
            button.clicked.connect(lambda _checked=False, value=hours: self.set_hours(value))
            self._range_row.addWidget(button)
            self._range_buttons.append((button, hours))
        self._range_row.addStretch(1)
        layout.addLayout(self._range_row)

        self.chart = HistoryChart(config, self)
        layout.addWidget(self.chart, 1)

        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.worst_label = QLabel(self)
        self.worst_label.setWordWrap(True)
        layout.addWidget(self.worst_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.mark_button = QPushButton(tr("menu.mark"), self)
        self.mark_button.clicked.connect(self.markRequested.emit)
        buttons.insertWidget(1, self.mark_button)

        self.copy_button = QPushButton(tr("history.copy"), self)
        self.copy_button.clicked.connect(self.copyRequested.emit)
        buttons.addWidget(self.copy_button)
        self.export_button = QPushButton(tr("history.export"), self)
        self.export_button.setDefault(True)
        self.export_button.clicked.connect(self.exportRequested.emit)
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

        self.refresh()

    # ------------------------------------------------------------------ state
    def apply_config(self, config: Config) -> None:
        """Settings are replaced wholesale on apply, so take the new object."""
        self._config = config
        self.chart.set_config(config)
        self.refresh()

    def hours(self) -> Optional[float]:
        return self._hours

    def set_hours(self, hours: Optional[float]) -> None:
        self._hours = hours
        for button, value in self._range_buttons:
            button.setChecked(value == hours)
        self.refresh()

    def refresh(self) -> None:
        """Redraw from the history object; safe to call on every new sample."""
        buckets = self._history.buckets(self._hours)
        self.chart.set_data(buckets, self._history.bucket_s,
                            self._history.markers(self._hours))
        self.summary_label.setText(self.summary_text())
        self.worst_label.setText(f"{tr('report.worst')}: "
                                 f"{worst_hour_line(self._history.worst_hour(self._hours))}")

    def summary_text(self) -> str:
        summary = self._history.summary(self._hours)
        uptime = 100.0 - (summary.get("loss_pct") or 0.0)
        parts = [
            f"{tr('label.avg')} {format_ms(summary.get('avg_ms'))}",
            f"{tr('label.p95')} {format_ms(summary.get('p95_ms'))}",
            f"{tr('label.range')} {format_ms(summary.get('min_ms'))}"
            f" – {format_ms(summary.get('max_ms'))}",
            f"{tr('label.jitter')} {format_ms(summary.get('jitter_ms'))}",
            f"{tr('report.uptime')} {uptime:.1f}%",
            f"{tr('report.stalls')} {summary.get('stalls', 0)}",
            f"{tr('report.spikes')} {summary.get('spikes', 0)}",
        ]
        return "   ·   ".join(parts)


def _runs(rows: Sequence[Bucket], bucket_s: float) -> List[List[Bucket]]:
    """Stretches with no missing minutes: never draw a line across a gap."""
    runs: List[List[Bucket]] = []
    current: List[Bucket] = []
    for row in rows:
        if current and row.start - current[-1].start > bucket_s * 2.5:
            runs.append(current)
            current = []
        current.append(row)
    if current:
        runs.append(current)
    return [run for run in runs if len(run) >= 1]
