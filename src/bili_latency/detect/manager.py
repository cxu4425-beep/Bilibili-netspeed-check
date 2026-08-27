"""Combining the detection sources into one answer: what are you watching?

Priority, highest first:

1. **bridge** - the page itself reported in through the userscript;
2. **on-screen title** - a window that is open right now identifies the page,
   either because a history entry carries that title, or because the title was
   learned earlier from a copied link (this is what makes the official desktop
   client work, since it exposes a title but no URL);
3. **newest evidence** - whichever is more recent, the last Bilibili link found
   in the clipboard or the newest visited page in the browser history.

Every source is optional. With all of them off (or nothing found) the monitor
falls back to whatever is configured manually.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from ..models import WatchTarget
from . import history as history_source
from . import titles as title_source
from .bridge import BridgeServer
from .clipboard import expand_short_link, extract_bilibili_url, is_short_link
from .urls import target_from_url

LOG = logging.getLogger(__name__)


class AutoDetector:
    """Polls the enabled sources, cheaply, and remembers the last answer."""

    def __init__(self, config, memory_path: Optional[Path] = None,
                 url_resolver: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self._config = config
        self._bridge: Optional[BridgeServer] = None
        self._last_scan = 0.0
        self._last_target: Optional[WatchTarget] = None
        self._history_failures = 0
        self._lock = threading.Lock()
        self._clipboard_target: Optional[WatchTarget] = None
        self._seen_clipboard = ""
        self._memory = title_source.TitleMemory(memory_path)
        self._url_resolver = url_resolver
        self.apply_config(config)

    # ------------------------------------------------------------------ config
    def apply_config(self, config) -> None:
        self._config = config
        if config.enabled and config.use_bridge:
            if self._bridge is not None and self._bridge.port != config.bridge_port:
                self._bridge.stop()
                self._bridge = None
            if self._bridge is None:
                self._bridge = BridgeServer(config.bridge_port, config.bridge_timeout_s)
            self._bridge.timeout_s = float(config.bridge_timeout_s)
            self._bridge.start()
        elif self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
        self._last_scan = 0.0
        self._history_failures = 0

    def set_url_resolver(self, resolver: Optional[Callable[[str], Optional[str]]]) -> None:
        """Injected by the monitor so short links can be followed."""
        self._url_resolver = resolver

    def close(self) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
        self._memory.save()

    @property
    def bridge_running(self) -> bool:
        return self._bridge is not None and self._bridge.running

    @property
    def last_target(self) -> Optional[WatchTarget]:
        return self._last_target

    @property
    def remembered_titles(self) -> int:
        return len(self._memory)

    # -------------------------------------------------------------- clipboard
    def submit_clipboard(self, text: str) -> Optional[WatchTarget]:
        """Offer clipboard text; returns the target when it holds a Bilibili link.

        Called from the monitor thread (the UI thread only reads the clipboard),
        because a b23.tv link has to be resolved over the network first.
        """
        if not self._config.use_clipboard:
            return None
        text = (text or "").strip()
        if not text or text == self._seen_clipboard:
            return None
        self._seen_clipboard = text

        url = extract_bilibili_url(text)
        if url is None:
            return None
        if is_short_link(url):
            if self._url_resolver is None:
                return None
            url = expand_short_link(self._url_resolver, url) or ""
        target = target_from_url(url, source="clipboard")
        if target is None:
            return None
        with self._lock:
            self._clipboard_target = target
        # A link the user just copied is the freshest evidence there is: apply it
        # now instead of waiting for the next scheduled scan.
        self._last_target = target
        self._last_scan = 0.0
        LOG.info("clipboard points at %s %s", target.kind, target.ident)
        self._learn_from(target)
        return target

    def _learn_from(self, target: WatchTarget) -> None:
        """Pair the app window in front with the link we just resolved."""
        if not self._config.remember_titles or target.is_empty:
            return
        title = title_source.foreground_title()
        if self._memory.remember(title, target.kind, target.ident, target.page):
            LOG.info("remembered window title %r for %s %s", title, target.kind, target.ident)

    # ------------------------------------------------------------------- poll
    def poll(self, force: bool = False) -> Optional[WatchTarget]:
        """Best current target, or ``None`` when no source has an opinion.

        Cheap to call every round: the expensive history scan is rate limited to
        ``poll_interval_s`` and the previous answer is returned in between.
        """
        config = self._config
        if not config.enabled:
            self._last_target = None
            return None

        if self._bridge is not None:
            reported = self._bridge.latest()
            if reported is not None:
                self._learn_from(reported)
                self._last_target = reported
                return reported

        now = time.monotonic()
        interval = max(2, int(config.poll_interval_s))
        if not force and (now - self._last_scan) < interval:
            return self._last_target
        self._last_scan = now

        target = self._best_offline_target()
        if target is not None:
            self._last_target = target
        return self._last_target

    def _best_offline_target(self) -> Optional[WatchTarget]:
        config = self._config
        entries = self._history_entries() if config.use_history else []
        open_titles = title_source.window_titles() if config.use_titles else []

        # 1. A window on screen right now tells us the page - best evidence
        #    short of the page itself reporting in.
        if open_titles:
            for entry, target in entries:
                if title_source.title_matches(entry.title, open_titles):
                    return _retag(target, "history+title")
            if config.remember_titles:
                remembered = self._memory.lookup(open_titles)
                if remembered:
                    return WatchTarget(
                        kind=remembered.get("kind", ""), ident=remembered.get("ident", ""),
                        page=int(remembered.get("page", 1) or 1), source="title",
                    )

        # 2. Otherwise the most recent thing we know about wins: a link copied
        #    out of the desktop client, or the newest page in the history.
        with self._lock:
            clipboard = self._clipboard_target
        newest_history = entries[0][1] if entries else None
        candidates = [item for item in (clipboard, newest_history) if item is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda target: target.detected_at)

    def _history_entries(self) -> list:
        try:
            entries = history_source.scan(window_s=self._config.history_window_min * 60.0)
            self._history_failures = 0
        except Exception as exc:  # never let a browser profile break the loop
            self._history_failures += 1
            if self._history_failures <= 3:
                LOG.warning("history detection failed: %s", exc)
            return []
        pairs = []
        for entry in entries:
            target = target_from_url(entry.url, title=entry.title, source="history",
                                     ts=entry.visited_at)
            if target is not None:
                pairs.append((entry, target))
        return pairs


def _retag(target: WatchTarget, source: str) -> WatchTarget:
    return WatchTarget(kind=target.kind, ident=target.ident, page=target.page,
                       title=target.title, source=source, detected_at=target.detected_at)
