import json

import pytest

from lagscope.config import Config, app_config_dir, config_path, parse_room_id


@pytest.mark.parametrize(
    "text,expected",
    [
        ("21452505", "21452505"),
        ("  123  ", "123"),
        ("https://live.bilibili.com/21452505", "21452505"),
        ("https://live.bilibili.com/blanc/1234?broadcast_type=0", "1234"),
        ("http://live.bilibili.com/h5/9999", "9999"),
        ("https://www.bilibili.com/video/BV1xx", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_parse_room_id(text, expected):
    assert parse_room_id(text) == expected


def test_save_and_load_roundtrip():
    config = Config()
    config.room_id = "https://live.bilibili.com/555"
    config.overlay.theme = "pink"
    config.overlay.x = 314
    config.sanitized().save()

    loaded = Config.load()
    assert loaded.room_id == "555"
    assert loaded.overlay.theme == "pink"
    assert loaded.overlay.x == 314
    assert loaded.probe.interval_ms == Config().probe.interval_ms


def test_unknown_keys_are_ignored():
    config = Config.from_dict({"room_id": "1", "nope": True, "overlay": {"theme": "light", "nope": 2}})
    assert config.room_id == "1"
    assert config.overlay.theme == "light"


def test_sanitize_clamps_out_of_range_values():
    config = Config()
    config.probe.interval_ms = 5
    config.overlay.opacity = 9.0
    config.overlay.scale = 0.01
    config.overlay.theme = "rainbow"
    config.overlay.anchor_mode = "orbit"
    config.thresholds.good_ms = 4000
    config.thresholds.warn_ms = 100
    config.sanitized()

    assert config.probe.interval_ms == 500
    assert config.overlay.opacity == 1.0
    assert config.overlay.scale == 0.6
    assert config.overlay.theme == "dark"
    assert config.overlay.anchor_mode == "free"
    assert config.thresholds.warn_ms >= config.thresholds.good_ms


def test_corrupt_config_is_quarantined_not_fatal():
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")

    config = Config.load()

    assert config.room_id == ""
    assert path.with_suffix(".json.broken").exists()


def test_save_is_atomic_and_leaves_no_temp_files():
    Config().save()
    leftovers = [p.name for p in app_config_dir().iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    assert json.loads(config_path().read_text(encoding="utf-8"))["version"] == 1


def test_every_nested_section_is_registered():
    """A section missing from _NESTED silently loads back as a plain dict.

    Nothing raises: attribute access fails much later, somewhere unrelated, and
    only once that section is actually read. Adding a section and forgetting
    the table is a one-line mistake with no local symptom, so it is checked
    here rather than left to be found in the field.
    """
    import dataclasses

    from lagscope.config import Config, _NESTED

    for info in dataclasses.fields(Config):
        default = info.default_factory if info.default_factory is not dataclasses.MISSING else None
        if default is None:
            continue
        value = default()
        if dataclasses.is_dataclass(value):
            assert info.name in _NESTED, f"config section {info.name!r} is not in _NESTED"
            assert _NESTED[info.name] is type(value)
