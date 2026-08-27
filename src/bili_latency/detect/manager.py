"""Combining the detection sources into one answer: what are you watching?

Priority, highest first:

1. **bridge** - the page itself reported in through the userscript;
2. **history + window title** - the newest visited Bilibili page that is also
   the title of a window currently on screen (so switching tabs is followed);
3. **history** - the most recently visited Bilibili page inside the time window.

Every source is optional. With all of them off (or nothing found) the monitor
falls back to whatever is configured manually.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ..models import WatchTarget
from . import history as history_source
from . import titles as title_source
from .bridge import BridgeServer
from .urls import target_from_url

LOG = logging.getLogger(__name__)


class AutoDetector:
    """Polls the enabled sources, cheaply, and remembers the last answer."""

    def __init__(self, config) -> None:
        self._config = config
        self._bridge: Optional[BridgeServer] = None
        self._last_scan = 0.0
        self._last_target: Optional[WatchTarget] = None
        self._history_failures = 0
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

    def close(self) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None

    @property
    def bridge_running(self) -> bool:
        return self._bridge is not None and self._bridge.running

    @property
    def last_target(self) -> Optional[WatchTarget]:
        return self._last_target

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
                self._last_target = reported
                return reported

        now = time.monotonic()
        interval = max(2, int(config.poll_interval_s))
        if not force and (now - self._last_scan) < interval:
            return self._last_target
        self._last_scan = now

        target = self._scan_history() if config.use_history else None
        if target is not None:
            self._last_target = target
        return self._last_target

    def _scan_history(self) -> Optional[WatchTarget]:
        config = self._config
        try:
            entries = history_source.scan(window_s=config.history_window_min * 60.0)
            self._history_failures = 0
        except Exception as exc:  # never let a browser profile break the loop
            self._history_failures += 1
            if self._history_failures <= 3:
                LOG.warning("history detection failed: %s", exc)
            return None

        watchable = [
            (entry, target)
            for entry, target in (
                (entry, target_from_url(entry.url, title=entry.title, source="history",
                                        ts=entry.visited_at))
                for entry in entries
            )
            if target is not None
        ]
        if not watchable:
            return None

        if config.use_titles:
            open_titles = title_source.window_titles()
            if open_titles:
                for entry, target in watchable:
                    if title_source.title_matches(entry.title, open_titles):
                        return WatchTarget(
                            kind=target.kind, ident=target.ident, page=target.page,
                            title=target.title, source="history+title",
                            detected_at=target.detected_at,
                        )

        return watchable[0][1]
