"""Working out what the user is watching right now, without a browser plugin."""

from .manager import AutoDetector
from .urls import target_from_url

__all__ = ["AutoDetector", "target_from_url"]
