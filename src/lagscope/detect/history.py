"""Reading the newest Bilibili page out of the local browser history.

This is how the monitor knows which room or video you are watching without a
browser extension. It is deliberately narrow:

* the history file is **copied** to a temporary file and opened **read-only**,
  so a running browser is never disturbed and nothing is ever written back;
* only rows whose URL contains ``bilibili.com`` are read;
* only rows visited inside the configured time window are considered;
* nothing leaves the machine - the result is a room id or a BV id, nothing else.

Users who would rather not have their history read can turn this source off in
the settings, or use the userscript bridge instead.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

LOG = logging.getLogger(__name__)

# Chromium timestamps count microseconds since 1601-01-01.
_CHROME_EPOCH_OFFSET = 11_644_473_600

CHROMIUM_BROWSERS = {
    "chrome": {
        "win": r"Google\Chrome\User Data",
        "darwin": "Google/Chrome",
        "linux": "google-chrome",
    },
    "edge": {
        "win": r"Microsoft\Edge\User Data",
        "darwin": "Microsoft Edge",
        "linux": "microsoft-edge",
    },
    "brave": {
        "win": r"BraveSoftware\Brave-Browser\User Data",
        "darwin": "BraveSoftware/Brave-Browser",
        "linux": "BraveSoftware/Brave-Browser",
    },
    "vivaldi": {"win": r"Vivaldi\User Data", "darwin": "Vivaldi", "linux": "vivaldi"},
    "chromium": {"win": r"Chromium\User Data", "darwin": "Chromium", "linux": "chromium"},
}

_PROFILE_HINTS = ("Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4")


@dataclass(frozen=True)
class HistoryEntry:
    url: str
    title: str
    visited_at: float             # epoch seconds
    browser: str = ""


def chromium_time_to_epoch(value: int) -> float:
    return (value or 0) / 1_000_000.0 - _CHROME_EPOCH_OFFSET


def firefox_time_to_epoch(value: int) -> float:
    return (value or 0) / 1_000_000.0


def _base_dir() -> tuple[Path, str]:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")), "win"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support", "darwin"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"), "linux"


def chromium_history_files() -> list[tuple[str, Path]]:
    """Every ``History`` database of every installed Chromium-family browser."""
    base, key = _base_dir()
    found: list[tuple[str, Path]] = []
    for browser, paths in CHROMIUM_BROWSERS.items():
        root = base / paths[key]
        if not root.is_dir():
            continue
        candidates = [root / hint for hint in _PROFILE_HINTS]
        try:
            candidates += [child for child in root.iterdir() if child.is_dir()]
        except OSError:
            pass
        seen: set = set()
        for profile in candidates:
            database = profile / "History"
            if database in seen or not database.is_file():
                continue
            seen.add(database)
            found.append((browser, database))
    return found


def firefox_history_files() -> list[tuple[str, Path]]:
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA", Path.home())) / "Mozilla" / "Firefox" / "Profiles"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
    else:
        root = Path.home() / ".mozilla" / "firefox"
    if not root.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    try:
        for profile in root.iterdir():
            database = profile / "places.sqlite"
            if database.is_file():
                found.append(("firefox", database))
    except OSError:
        pass
    return found


def _copy_for_reading(database: Path, into: Path) -> Optional[Path]:
    """Copy the database (plus its WAL sidecars) so a locked file can be read."""
    try:
        target = into / database.name
        shutil.copy2(database, target)
        for suffix in ("-wal", "-shm"):
            sidecar = database.with_name(database.name + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, into / sidecar.name)
        return target
    except OSError as exc:
        LOG.debug("cannot copy %s: %s", database, exc)
        return None


def read_history(database: Path, browser: str = "", limit: int = 25,
                 firefox: bool = False) -> list[HistoryEntry]:
    """Newest Bilibili rows from one history database."""
    with tempfile.TemporaryDirectory(prefix="bili-hist-") as tmp:
        copy = _copy_for_reading(database, Path(tmp))
        if copy is None:
            return []
        if firefox:
            query = (
                "SELECT url, COALESCE(title, ''), COALESCE(last_visit_date, 0) FROM moz_places "
                "WHERE url LIKE '%bilibili.com%' AND last_visit_date IS NOT NULL "
                "ORDER BY last_visit_date DESC LIMIT ?"
            )
            convert = firefox_time_to_epoch
        else:
            query = (
                "SELECT url, COALESCE(title, ''), COALESCE(last_visit_time, 0) FROM urls "
                "WHERE url LIKE '%bilibili.com%' ORDER BY last_visit_time DESC LIMIT ?"
            )
            convert = chromium_time_to_epoch
        try:
            connection = sqlite3.connect(f"file:{copy}?mode=ro", uri=True, timeout=2.0)
        except sqlite3.Error as exc:
            LOG.debug("cannot open %s: %s", database, exc)
            return []
        try:
            rows = connection.execute(query, (limit,)).fetchall()
        except sqlite3.Error as exc:
            LOG.debug("history query failed for %s: %s", database, exc)
            return []
        finally:
            connection.close()
    return [
        HistoryEntry(url=row[0], title=row[1], visited_at=convert(row[2]), browser=browser)
        for row in rows
        if row and row[0]
    ]


def scan(window_s: float = 1800.0, limit_per_profile: int = 25,
         databases: Optional[Iterable[tuple]] = None) -> list[HistoryEntry]:
    """Recent Bilibili visits across every browser, newest first."""
    if databases is None:
        databases = [(browser, path, False) for browser, path in chromium_history_files()]
        databases += [(browser, path, True) for browser, path in firefox_history_files()]
    cutoff = time.time() - max(60.0, window_s)
    entries: list[HistoryEntry] = []
    for browser, path, is_firefox in databases:
        try:
            entries.extend(
                entry for entry in read_history(path, browser, limit_per_profile, is_firefox)
                if entry.visited_at >= cutoff
            )
        except Exception as exc:  # a broken profile must not kill detection
            LOG.debug("history scan failed for %s: %s", path, exc)
    entries.sort(key=lambda entry: entry.visited_at, reverse=True)
    return entries
