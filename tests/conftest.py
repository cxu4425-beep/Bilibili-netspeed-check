import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path, monkeypatch):
    """Never touch the developer's real config while testing."""
    monkeypatch.setenv("BILI_LATENCY_CONFIG_DIR", str(tmp_path / "config"))
    yield tmp_path
