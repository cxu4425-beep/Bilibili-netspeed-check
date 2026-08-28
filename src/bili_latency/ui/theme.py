"""Colours and number formatting shared by the overlay and the tray icon."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Palette:
    """Solid 6-digit colours only.

    Qt reads an 8-digit hex string as #AARRGGBB, which silently turns a CSS
    style #RRGGBBAA value into a nearly invisible one; window-level opacity is
    applied separately from the config instead.
    """

    background: str
    foreground: str
    muted: str
    border: str
    accent: str
    good: str
    warn: str
    bad: str


THEMES: dict[str, Palette] = {
    "dark": Palette(
        background="#12141a", foreground="#f4f6fb", muted="#9aa3b5",
        border="#2b303c", accent="#00a1d6", good="#3fd07f", warn="#f6c445", bad="#ff5d5d",
    ),
    "light": Palette(
        background="#ffffff", foreground="#1a1d24", muted="#5c6474",
        border="#d8dde7", accent="#00a1d6", good="#1f9d55", warn="#c98a00", bad="#d93636",
    ),
    "pink": Palette(
        background="#2a1420", foreground="#ffeef6", muted="#d9a7bf",
        border="#4a2536", accent="#fb7299", good="#5fd3a0", warn="#ffd166", bad="#ff6b8b",
    ),
}


def palette_for(name: str) -> Palette:
    return THEMES.get(name, THEMES["dark"])


def level_for(value: Optional[float], good_ms: float, warn_ms: float) -> str:
    """Return ``good`` / ``warn`` / ``bad`` / ``unknown`` for a latency value."""
    if value is None:
        return "unknown"
    if value <= good_ms:
        return "good"
    if value <= warn_ms:
        return "warn"
    return "bad"


def color_for_level(palette: Palette, level: str) -> str:
    return {
        "good": palette.good,
        "warn": palette.warn,
        "bad": palette.bad,
    }.get(level, palette.muted)


def format_ms(value: Optional[float], placeholder: str = "--") -> str:
    """Human readable latency: ``482 ms`` / ``2.41 s`` / ``1 m 05 s``."""
    if value is None:
        return placeholder
    if value < 0:
        value = 0.0
    if value < 1000:
        return f"{value:.0f} ms"
    if value < 60_000:
        return f"{value / 1000.0:.2f} s"
    minutes, seconds = divmod(value / 1000.0, 60)
    return f"{int(minutes)} m {seconds:04.1f} s"


def format_mbps(value: Optional[float], placeholder: str = "--") -> str:
    """Download speed: ``820 kbps`` / ``24.3 Mbps`` / ``1.20 Gbps``."""
    if value is None:
        return placeholder
    if value < 1:
        return f"{value * 1000:.0f} kbps"
    if value < 1000:
        return f"{value:.1f} Mbps"
    return f"{value / 1000:.2f} Gbps"


def format_mbps_short(value: Optional[float], placeholder: str = "--") -> str:
    """Speed for the cramped stats row: ``820k`` / ``44M`` / ``1.2G``."""
    if value is None:
        return placeholder
    if value < 1:
        return f"{value * 1000:.0f}k"
    if value < 100:
        return f"{value:.1f}M"
    if value < 1000:
        return f"{value:.0f}M"
    return f"{value / 1000:.1f}G"


def format_ms_short(value: Optional[float], placeholder: str = "--") -> str:
    """Compact form used inside the tray icon (max 4 glyphs)."""
    if value is None:
        return placeholder
    if value < 1000:
        return f"{value:.0f}"
    if value < 10_000:
        return f"{value / 1000.0:.1f}s"
    if value < 100_000:
        return f"{value / 1000.0:.0f}s"
    return "99s"
