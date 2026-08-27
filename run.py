#!/usr/bin/env python3
"""Run the monitor straight from a checkout, without installing anything.

    python run.py --room 21452505
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from bili_latency.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
