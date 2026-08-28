"""Using open window titles to tell which history entry is the current page.

The history database knows every Bilibili page you visited; the window titles
know which one is on screen *now*. Matching one against the other is what makes
auto-detection follow you when you switch tabs instead of sticking to whatever
you opened last.

Window enumeration is implemented on Windows only (see ui/anchor.py). Elsewhere
this returns nothing and the detector falls back to "most recently visited".
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ..ui.anchor import create_window_finder

LOG = logging.getLogger(__name__)

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


def foreground_title() -> str:
    """Title of the window the user is in right now (empty where unsupported)."""
    finder = create_window_finder()
    if not finder.available:
        return ""
    return finder.foreground_title()


# A window called just "哔哩哔哩" says nothing about which room is open, so
# titles like these are never learned or matched against.
GENERIC_TITLES = frozenset({
    "哔哩哔哩", "嗶哩嗶哩", "bilibili", "哔哩哔哩弹幕视频网", "哔哩哔哩直播",
    "bilibili直播", "哔哩哔哩客户端", "bilibili客户端", "b站",
})
# A title has to look like a Bilibili app window before a link gets attached to it,
# otherwise copying a link out of a chat app would teach the wrong window.
APP_MARKERS = ("哔哩哔哩", "嗶哩嗶哩", "bilibili", "b23")


def is_distinctive(title: str) -> bool:
    """True when a title identifies a specific page, not just the app."""
    normalized = normalize_title(title)
    if len(normalized) < _MIN_MATCH_CHARS:
        return False
    return normalized.lower() not in {name.lower() for name in GENERIC_TITLES}


def looks_like_bilibili_app(title: str) -> bool:
    lowered = (title or "").lower()
    return any(marker in lowered for marker in APP_MARKERS)


class TitleMemory:
    """Remembers which window title belonged to which room or video.

    The official desktop client does not expose a URL, but its window title
    changes with the room. Once a title has been paired with a link (from the
    clipboard or the userscript), coming back to that room is recognised from
    the title alone - no browser and no scraping involved.
    """

    def __init__(self, path: Optional[Path] = None, limit: int = 200) -> None:
        self.path = path
        self.limit = max(10, int(limit))
        self._entries: dict[str, dict] = {}
        self._dirty = False
        self.load()

    # ------------------------------------------------------------------- disk
    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            LOG.debug("title memory unreadable, starting empty")
            return
        if isinstance(data, dict):
            self._entries = {
                str(key): value for key, value in data.items() if isinstance(value, dict)
            }

    def save(self) -> None:
        if self.path is None or not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._entries, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._dirty = False
        except OSError as exc:
            LOG.debug("could not save title memory: %s", exc)

    # ------------------------------------------------------------------ usage
    def remember(self, title: str, kind: str, ident: str, page: int = 1) -> bool:
        """Pair a window title with a target; returns True when stored."""
        if not ident or not is_distinctive(title) or not looks_like_bilibili_app(title):
            return False
        key = normalize_title(title)
        self._entries[key] = {"kind": kind, "ident": ident, "page": int(page),
                              "learned_at": time.time()}
        self._prune()
        self._dirty = True
        self.save()
        return True

    def lookup(self, titles: Sequence[str]) -> Optional[dict]:
        """The remembered target for any title currently on screen."""
        for title in titles:
            if not is_distinctive(title):
                continue
            entry = self._entries.get(normalize_title(title))
            if entry:
                return entry
        return None

    def _prune(self) -> None:
        if len(self._entries) <= self.limit:
            return
        ordered = sorted(self._entries.items(), key=lambda item: item[1].get("learned_at", 0.0))
        for key, _entry in ordered[: len(self._entries) - self.limit]:
            self._entries.pop(key, None)

    def __len__(self) -> int:
        return len(self._entries)
