#!/usr/bin/env python3
"""Build the standalone executable for the current platform.

    python packaging/build.py

Output lands in dist/ (BiliLatencyMonitor.exe on Windows,
BiliLatencyMonitor.app on macOS, BiliLatencyMonitor elsewhere).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is missing. Install it with:  pip install pyinstaller", file=sys.stderr)
        return 1

    # Regenerate the icons so the build always matches the drawing code.
    subprocess.run([sys.executable, str(ROOT / "assets" / "make_icon.py")], check=True, cwd=ROOT)

    command = [
        sys.executable, "-m", "PyInstaller",
        str(ROOT / "packaging" / "bili_latency.spec"),
        "--noconfirm",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
    ]
    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode == 0:
        print(f"\nDone. Look in {ROOT / 'dist'}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
