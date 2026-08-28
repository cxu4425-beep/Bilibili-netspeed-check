"""Icons drawn at runtime, so the app ships without binary image assets.

The same drawing code produces the window icon, the tray icon and (via
``assets/make_icon.py``) the .ico used by the Windows build.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap,
)

BILI_BLUE = "#00a1d6"
BILI_PINK = "#fb7299"


def app_pixmap(size: int = 256) -> QPixmap:
    """A gauge dial in the Bilibili blue/pink gradient."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    radius = size * 0.22
    rect = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor(BILI_BLUE))
    gradient.setColorAt(1.0, QColor(BILI_PINK))
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, QBrush(gradient))

    # Dial arc
    dial = QRectF(size * 0.22, size * 0.24, size * 0.56, size * 0.56)
    pen = QPen(QColor(255, 255, 255, 235), size * 0.075)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawArc(dial, 200 * 16, -220 * 16)

    # Needle
    painter.setPen(QPen(QColor(255, 255, 255), size * 0.06, Qt.SolidLine, Qt.RoundCap))
    center_x = dial.center().x()
    center_y = dial.center().y() + size * 0.02
    painter.drawLine(
        int(center_x), int(center_y),
        int(center_x + dial.width() * 0.34), int(center_y - dial.height() * 0.28),
    )
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(center_x - size * 0.045, center_y - size * 0.045, size * 0.09, size * 0.09))
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_pixmap(size))
    return icon


def value_pixmap(text: str, color: str, size: int = 64, background: Optional[str] = None) -> QPixmap:
    """Tray icon showing the current latency, colour coded."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    rect = QRectF(1, 1, size - 2, size - 2)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.22, size * 0.22)
    painter.fillPath(path, QBrush(QColor(background or "#101318")))
    painter.setPen(QPen(QColor(color), max(1.0, size * 0.05)))
    painter.drawPath(path)

    font = _fitted_font(text, size)
    painter.setFont(font)
    painter.setPen(QPen(QColor(color)))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
    painter.end()
    return pixmap


def _fitted_font(text: str, size: int) -> QFont:
    """Largest bold font whose text still fits inside the rounded square."""
    available = size * 0.76
    font = QFont()
    font.setBold(True)
    pixel_size = max(6, int(size * 0.52))
    while pixel_size > 6:
        font.setPixelSize(pixel_size)
        metrics = QFontMetrics(font)
        if metrics.horizontalAdvance(text) <= available and metrics.height() <= size * 0.82:
            break
        pixel_size -= 1
    font.setPixelSize(max(6, pixel_size))
    return font


def value_icon(text: str, color: str, background: Optional[str] = None) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 64):
        icon.addPixmap(value_pixmap(text, color, size, background))
    return icon
