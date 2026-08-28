"""Reading what the official Bilibili desktop client is playing.

The client has no address bar and writes nothing to the browser's history, but
it is a Chromium-based app, so it keeps its own data folder. Two things in
there give the current room or video away without asking the user for anything:

* a Chromium-style ``History`` database - exactly the schema the browser
  sources already read, so the same read-only copy trick works;
* the client's own log files, which mention room ids and BV ids as it plays.

Both are read-only and filtered down to Bilibili ids before anything is kept.
Where the client stores its data differs between versions, so the folders are
discovered rather than hard-coded, extra folders can be added in the config,
and ``lagscope --detect-report`` prints what was actually found on this
machine.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from .history import HistoryEntry, read_history

LOG = logging.getLogger(__name__)

# Folder names the client has shipped under, relative to %APPDATA% and
# %LOCALAPPDATA% (and the equivalent locations on macOS).
CLIENT_FOLDER_NAMES = (
    "bilibili", "BiliBili", "哔哩哔哩", "嗶哩嗶哩",
    "bilibili-desktop", "bilibiliPC", "BilibiliPC", "bili-desktop",
)
# Sub-folders that never hold anything useful but do hold thousands of files.
SKIP_DIRS = frozenset({
    "Cache", "Code Cache", "GPUCache", "ShaderCache", "DawnCache", "GrShaderCache",
    "Service Worker", "IndexedDB", "blob_storage", "Crashpad", "component_crx_cache",
    "extensions_crx_cache", "Media Cache", "Application Cache", "Dictionaries",
})
MAX_DEPTH = 4
MAX_LOG_FILES = 12
LOG_TAIL_BYTES = 256 * 1024
LOG_SUFFIXES = (".log", ".txt")

_ROOM_PATTERNS = (
    re.compile(r"live\.bilibili\.com/(?:blanc/|h5/)?(\d{1,12})"),
    re.compile(r'"?room[_-]?id"?\s*[=:]\s*"?(\d{3,12})"?', re.IGNORECASE),
    re.compile(r'"?roomid"?\s*[=:]\s*"?(\d{3,12})"?', re.IGNORECASE),
)
_VIDEO_PATTERNS = (
    re.compile(r"bilibili\.com/video/(BV[0-9A-Za-z]{10})"),
    re.compile(r'"?bvid"?\s*[=:]\s*"?(BV[0-9A-Za-z]{10})"?', re.IGNORECASE),
)


def client_roots(extra: Iterable[str] = ()) -> list[Path]:
    """Candidate data folders of the official client, newest-looking first."""
    roots: list[Path] = []
    for path in extra:
        candidate = Path(os.path.expandvars(str(path))).expanduser()
        if candidate.is_dir():
            roots.append(candidate)

    bases: list[Path] = []
    if sys.platform.startswith("win"):
        for variable in ("APPDATA", "LOCALAPPDATA"):
            value = os.environ.get(variable)
            if value:
                bases.append(Path(value))
    elif sys.platform == "darwin":
        bases.append(Path.home() / "Library" / "Application Support")
    else:
        bases.append(Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"))

    for base in bases:
        for name in CLIENT_FOLDER_NAMES:
            candidate = base / name
            if candidate.is_dir():
                roots.append(candidate)
        # The Store (UWP) build lives under Packages\<something bilibili>.
        packages = base / "Packages"
        if packages.is_dir():
            try:
                for child in packages.iterdir():
                    lowered = child.name.lower()
                    if child.is_dir() and ("bilibili" in lowered or "哔哩哔哩" in child.name):
                        roots.append(child)
            except OSError:
                pass

    unique: list[Path] = []
    seen = set()
    for root in roots:
        resolved = str(root)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(root)
    return unique


def _walk(root: Path, depth: int = 0):
    """Yield files under ``root``, skipping cache trees and going no deeper."""
    if depth > MAX_DEPTH:
        return
    try:
        children = list(root.iterdir())
    except OSError:
        return
    for child in children:
        try:
            if child.is_dir():
                if child.name in SKIP_DIRS:
                    continue
                yield from _walk(child, depth + 1)
            else:
                yield child
        except OSError:
            continue


def find_history_databases(roots: Iterable[Path]) -> list[Path]:
    """Chromium ``History`` databases inside the client's data folders."""
    found: list[Path] = []
    for root in roots:
        for path in _walk(root):
            if path.name == "History" and path.suffix == "":
                found.append(path)
    return found


def find_log_files(roots: Iterable[Path], max_age_s: float) -> list[Path]:
    """Recently written log files, newest first."""
    cutoff = time.time() - max_age_s
    candidates: list[tuple[float, Path]] = []
    for root in roots:
        for path in _walk(root):
            if path.suffix.lower() not in LOG_SUFFIXES:
                continue
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified >= cutoff:
                candidates.append((modified, path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _modified, path in candidates[:MAX_LOG_FILES]]


def scan_log_file(path: Path, modified_at: Optional[float] = None) -> list[HistoryEntry]:
    """Room / video ids mentioned near the end of one log file.

    Only ids are taken out; no other line content is kept or logged. The file's
    modification time is used as the timestamp, so a log the client is still
    writing counts as current.
    """
    try:
        stamp = modified_at if modified_at is not None else path.stat().st_mtime
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - LOG_TAIL_BYTES))
            tail = handle.read().decode("utf-8", "replace")
    except OSError as exc:
        LOG.debug("cannot read client log %s: %s", path, exc)
        return []

    entries: list[HistoryEntry] = []
    for pattern in _VIDEO_PATTERNS:
        for match in pattern.finditer(tail):
            entries.append(HistoryEntry(
                url=f"https://www.bilibili.com/video/{match.group(1)}",
                title="", visited_at=stamp, browser="client-log",
            ))
    for pattern in _ROOM_PATTERNS:
        for match in pattern.finditer(tail):
            room = match.group(1)
            if room == "0":
                continue
            entries.append(HistoryEntry(
                url=f"https://live.bilibili.com/{room}",
                title="", visited_at=stamp, browser="client-log",
            ))
    # The last mention in the file is the most recent thing the client did.
    entries.reverse()
    return entries


class ClientScanner:
    """Finds the client's data folders once, then reads them cheaply."""

    REDISCOVER_INTERVAL_S = 600.0

    def __init__(self, extra_dirs: Iterable[str] = ()) -> None:
        self.extra_dirs = list(extra_dirs)
        self._roots: list[Path] = []
        self._databases: list[Path] = []
        self._discovered_at = 0.0

    def discover(self, force: bool = False) -> list[Path]:
        now = time.monotonic()
        if force or not self._roots or (now - self._discovered_at) > self.REDISCOVER_INTERVAL_S:
            self._roots = client_roots(self.extra_dirs)
            self._databases = find_history_databases(self._roots)
            self._discovered_at = now
            if self._roots:
                LOG.info("client data folders: %s", ", ".join(str(p) for p in self._roots))
        return self._roots

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    @property
    def databases(self) -> list[Path]:
        return list(self._databases)

    def scan(self, window_s: float = 1800.0, limit: int = 25) -> list[HistoryEntry]:
        """Recent Bilibili pages the client itself has been on, newest first."""
        self.discover()
        cutoff = time.time() - max(60.0, window_s)
        entries: list[HistoryEntry] = []

        for database in self._databases:
            try:
                entries.extend(
                    entry for entry in read_history(database, "client", limit)
                    if entry.visited_at >= cutoff
                )
            except Exception as exc:  # a locked or odd profile is not fatal
                LOG.debug("client history %s failed: %s", database, exc)

        if not entries:
            # No usable history database in this build: fall back to the logs.
            for path in find_log_files(self._roots, max_age_s=max(60.0, window_s)):
                entries.extend(entry for entry in scan_log_file(path) if entry.visited_at >= cutoff)

        entries.sort(key=lambda entry: entry.visited_at, reverse=True)
        return entries
