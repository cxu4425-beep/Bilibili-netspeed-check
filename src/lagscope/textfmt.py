"""Column alignment for text that may be CJK.

A monospaced column laid out with ``f"{text:<28}"`` counts characters, and a
Chinese glyph occupies two of them on screen. Any table built that way lines
up in English and comes out ragged in the languages this app is mostly used
in, which is exactly backwards.
"""

from __future__ import annotations

import unicodedata


def width(text: str) -> int:
    """Columns a string occupies in a monospaced view (CJK glyphs take two)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text: str, columns: int) -> str:
    """Left-align ``text`` in a field ``columns`` wide, measured on screen."""
    return text + " " * max(0, columns - width(text))
