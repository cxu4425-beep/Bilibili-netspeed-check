"""Optional CSV recording of every sample, with size-based rotation."""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from .config import log_dir
from .models import LatencySample

LOG = logging.getLogger(__name__)

HEADER = [
    "timestamp",
    "iso_time",
    "total_ms",
    "network_ms",
    "stream_ms",
    "display_ms",
    "ok",
    "estimated",
    "method",
    "host",
    "error",
]


class CsvRecorder:
    """Appends samples to ``latency.csv``; rotates when it gets too big."""

    def __init__(self, path: Optional[Path] = None, max_bytes: int = 8 * 1024 * 1024, backups: int = 3) -> None:
        self.path = path or (log_dir() / "latency.csv")
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.backups = max(0, int(backups))
        self._handle: Optional[TextIO] = None
        self._writer = None

    def _open(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        self._handle = open(self.path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._handle)
        if new_file:
            self._writer.writerow(HEADER)
            self._handle.flush()

    def write(self, sample: LatencySample) -> None:
        try:
            self._open()
            assert self._writer is not None and self._handle is not None
            self._writer.writerow(
                [
                    f"{sample.ts:.3f}",
                    datetime.fromtimestamp(sample.ts).isoformat(timespec="milliseconds"),
                    _fmt(sample.total_ms),
                    _fmt(sample.network_ms),
                    _fmt(sample.stream_ms),
                    _fmt(sample.display_ms),
                    int(sample.ok),
                    int(sample.estimated),
                    sample.method,
                    sample.host,
                    (sample.error or "").replace("\n", " ")[:120],
                ]
            )
            self._handle.flush()
            self._rotate_if_needed()
        except OSError as exc:
            LOG.warning("CSV recording disabled after error: %s", exc)
            self.close()

    def _backup_path(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}")

    def _rotate_if_needed(self) -> None:
        if self._handle is None or self._handle.tell() < self.max_bytes:
            return
        self.close()
        try:
            if self.backups == 0:
                self.path.unlink(missing_ok=True)
                return
            oldest = self._backup_path(self.backups)
            oldest.unlink(missing_ok=True)
            for index in range(self.backups - 1, 0, -1):
                source = self._backup_path(index)
                if source.exists():
                    os.replace(source, self._backup_path(index + 1))
            os.replace(self.path, self._backup_path(1))
        except OSError as exc:
            LOG.warning("CSV rotation failed: %s", exc)

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
        self._handle = None
        self._writer = None


def _fmt(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.1f}"
