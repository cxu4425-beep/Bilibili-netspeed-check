"""Placing the overlay: screen corners, and following another app's window.

Following a window needs per-platform APIs. Windows is implemented with
``user32`` through ctypes (no extra dependency); elsewhere the finder reports
itself unavailable and the overlay falls back to a screen corner.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import NamedTuple, Optional

LOG = logging.getLogger(__name__)


class WindowRect(NamedTuple):
    x: int
    y: int
    width: int
    height: int


def compute_anchor_position(
    rect: WindowRect, size: tuple[int, int], corner: str, offset_x: int, offset_y: int
) -> tuple[int, int]:
    """Position for a widget of ``size`` inside ``rect`` at ``corner``."""
    width, height = size
    if corner.endswith("left"):
        x = rect.x + offset_x
    else:
        x = rect.x + rect.width - width - offset_x
    if corner.startswith("top"):
        y = rect.y + offset_y
    else:
        y = rect.y + rect.height - height - offset_y
    return int(x), int(y)


def clamp_to_rect(position: tuple[int, int], size: tuple[int, int], rect: WindowRect,
                  margin: int = 8) -> tuple[int, int]:
    """Keep a widget from being dragged completely off a screen."""
    x, y = position
    width, height = size
    min_x = rect.x - width + margin * 4
    max_x = rect.x + rect.width - margin * 4
    min_y = rect.y
    max_y = rect.y + rect.height - margin * 3
    return int(max(min_x, min(max_x, x))), int(max(min_y, min(max_y, y)))


class WindowFinder:
    """Base class: never finds anything, always reports unavailable."""

    available = False

    def find(self, keyword: str) -> Optional[WindowRect]:
        return None


class Win32WindowFinder(WindowFinder):
    available = True

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._user32.SetProcessDPIAware()

    def find(self, keyword: str) -> Optional[WindowRect]:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return None
        found: list[WindowRect] = []

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _lparam):  # pragma: no cover - Windows only
            if not self._user32.IsWindowVisible(hwnd) or self._user32.IsIconic(hwnd):
                return True
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value or ""
            if keyword not in title.lower():
                return True
            rect = RECT()
            if not self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width > 200 and height > 150:
                found.append(WindowRect(rect.left, rect.top, width, height))
                return False
            return True

        try:
            self._user32.EnumWindows(enum_proc(callback), 0)
        except OSError as exc:  # pragma: no cover - Windows only
            LOG.debug("EnumWindows failed: %s", exc)
            return None
        return found[0] if found else None


def create_window_finder() -> WindowFinder:
    if sys.platform.startswith("win"):
        try:
            return Win32WindowFinder()
        except Exception as exc:  # pragma: no cover - Windows only
            LOG.warning("window following unavailable: %s", exc)
    return WindowFinder()
