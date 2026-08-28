"""UI helpers that carry logic worth testing without a display server."""

import pytest

from lagscope.i18n import LANGUAGES, STRINGS, detect_system_language, normalize, set_language, tr
from lagscope.ui.anchor import WindowRect, clamp_to_rect, compute_anchor_position
from lagscope.ui.theme import format_ms, format_ms_short, level_for, palette_for


@pytest.mark.parametrize(
    "corner,expected",
    [
        ("top-left", (120, 60)),
        ("top-right", (880, 60)),
        ("bottom-left", (120, 720)),
        ("bottom-right", (880, 720)),
    ],
)
def test_compute_anchor_position(corner, expected):
    rect = WindowRect(100, 50, 1000, 800)
    assert compute_anchor_position(rect, (200, 120), corner, 20, 10) == expected


def test_clamp_keeps_the_overlay_reachable():
    rect = WindowRect(0, 0, 1920, 1080)
    assert clamp_to_rect((-9999, -9999), (200, 120), rect) == (-168, 0)
    assert clamp_to_rect((99999, 99999), (200, 120), rect) == (1888, 1056)
    assert clamp_to_rect((300, 400), (200, 120), rect) == (300, 400)


@pytest.mark.parametrize(
    "value,expected",
    [(None, "--"), (0, "0 ms"), (482, "482 ms"), (2413, "2.41 s"), (65_000, "1 m 05.0 s")],
)
def test_format_ms(value, expected):
    assert format_ms(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(None, "--"), (82, "82"), (2413, "2.4s"), (12_400, "12s"), (500_000, "99s")],
)
def test_format_ms_short(value, expected):
    assert format_ms_short(value) == expected


def test_level_thresholds():
    assert level_for(None, 2000, 5000) == "unknown"
    assert level_for(1999, 2000, 5000) == "good"
    assert level_for(2000, 2000, 5000) == "good"
    assert level_for(4000, 2000, 5000) == "warn"
    assert level_for(9000, 2000, 5000) == "bad"


def test_palettes_are_opaque_six_digit_hex():
    # Qt reads 8-digit hex as #AARRGGBB, which silently breaks the colours.
    for name in ("dark", "light", "pink", "unknown-falls-back"):
        palette = palette_for(name)
        for value in vars(palette).values():
            assert len(value) == 7 and value.startswith("#"), value


def test_every_string_is_translated_into_every_language():
    for key, entry in STRINGS.items():
        assert len(entry) == len(LANGUAGES), key
        assert all(text.strip() for text in entry), key


def test_language_selection():
    assert normalize("zh-TW") == "zh_TW"
    assert normalize("zh_HK") == "zh_TW"
    assert normalize("zh_CN.UTF-8") == "zh_CN"
    assert normalize("en_US.UTF-8") == "en"
    assert normalize("de_DE") == ""
    assert detect_system_language(["", "de_DE", "zh_TW"]) == "zh_TW"
    assert detect_system_language(["ja_JP"]) == "zh_CN"

    set_language("en")
    assert tr("label.total") == "Total"
    set_language("zh_TW")
    assert tr("label.total") == "總延遲"
    assert tr("no.such.key") == "no.such.key"
    set_language("zh_CN")


def test_tray_tooltip_formatting_uses_named_fields():
    set_language("en")
    text = tr("tray.tooltip", title="T", total="1 s", network="2 ms", stream="1 s",
              display="3 ms", status="ok")
    assert "Total 1 s" in text and "Network 2 ms" in text
    set_language("zh_CN")
