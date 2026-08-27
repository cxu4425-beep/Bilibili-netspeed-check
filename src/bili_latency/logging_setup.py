"""Application logging: rotating file in the user's config dir + stderr."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from .config import log_dir

_configured = False


def setup_logging(level: int = logging.INFO, directory: Optional[Path] = None) -> Path:
    """Configure the root logger once; returns the log file path."""
    global _configured
    directory = directory or log_dir()
    log_file = directory / "app.log"
    if _configured:
        return log_file

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # A read-only or full disk must not stop the app from running.
        pass

    # A packaged Windows app has no stderr; guard against that.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _configured = True
    return log_file
