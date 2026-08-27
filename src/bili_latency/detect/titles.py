"""Using open window titles to tell which history entry is the current page.

The history database knows every Bilibili page you visited; the window titles
know which one is on screen *now*. Matching one against the other is what makes
auto-detection follow you when you switch tabs instead of sticking to whatever
you opened last.

Window enumeration is implemented on Windows only (see ui/anchor.py). Elsewhere
this returns nothing and the detector falls back to "most recently visited".
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

from ..ui.anchor import create_window_finder

# Browsers append their own name (and sometimes a tab count) to the page title.
_SUFFIXES = (
    " - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox",
    " — Mozilla Firefox", " - Brave", " - Vivaldi", " - Chromium", " - Opera",
    " - 360极速浏览器", " - QQ浏览器", " - 搜狗高速浏览器",
)
_TAB_COUNT_RE = re.compile(r"\s+(?:and \d+ more pages?|以及另外 \d+ 个页面)$", re.IGNORECASE)
_MIN_MATCH_CHARS = 6


def window_titles() -> list[str]:
    """Titles of the visible top-level windows (empty where unsupported)."""
    finder = create_window_finder()
    if not finder.available:
        return []
    return [title for title, _rect in finder.enumerate() if title]


def normalize_title(title: str) -> str:
    """Strip the browser's own decoration from a window title."""
    text = (title or "").strip()
    # Browser name first, then the "and N more pages" tail it hides behind.
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = _TAB_COUNT_RE.sub("", text)
    return text.strip().strip("-—·").strip()


def title_matches(page_title: str, titles: Sequence[str]) -> bool:
    """True when a page title appears in one of the open window titles."""
    needle = normalize_title(page_title)
    if len(needle) < _MIN_MATCH_CHARS:
        return False
    needle = needle.lower()
    for window_title in titles:
        haystack = normalize_title(window_title).lower()
        if not haystack:
            continue
        if needle in haystack or haystack in needle:
            return True
    return False


def pick_matching(entries: Iterable, titles: Sequence[str]) -> Optional[object]:
    """First entry (they arrive newest-first) whose title is on screen."""
    if not titles:
        return None
    for entry in entries:
        if title_matches(getattr(entry, "title", ""), titles):
            return entry
    return None
