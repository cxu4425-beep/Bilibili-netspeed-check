#!/usr/bin/env python3
"""Regenerate assets/icon.png and assets/icon.ico from the runtime drawing code.

Usage:  python assets/make_icon.py
Requires PySide6 (already a runtime dependency); runs headless.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import struct  # noqa: E402

from PySide6.QtCore import QBuffer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from bili_latency.ui.icons import app_pixmap  # noqa: E402

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(size: int) -> bytes:
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    app_pixmap(size).save(buffer, "PNG")
    buffer.close()
    return bytes(buffer.data())


def write_ico(path: Path) -> None:
    """Write a multi-resolution .ico with PNG-compressed entries (Vista+)."""
    images = [(size, png_bytes(size)) for size in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = bytearray()
    for size, data in images:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(entries)
        for _size, data in images:
            handle.write(data)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    out_dir = ROOT / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    app_pixmap(256).save(str(out_dir / "icon.png"), "PNG")
    write_ico(out_dir / "icon.ico")
    print(f"wrote {out_dir / 'icon.png'} and {out_dir / 'icon.ico'}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
