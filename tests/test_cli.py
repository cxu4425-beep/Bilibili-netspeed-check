import pytest

from lagscope.cli import build_parser, main


def test_parser_accepts_the_documented_flags():
    args = build_parser().parse_args(
        ["--room", "https://live.bilibili.com/123", "--lang", "en", "--no-tray", "--probe-once"]
    )
    assert args.room == "https://live.bilibili.com/123"
    assert args.lang == "en"
    assert args.no_tray and args.probe_once
    assert args.log_level == "INFO"


def test_parser_rejects_an_unknown_language():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--lang", "fr"])


def test_main_rejects_a_room_that_is_not_a_room(capsys):
    assert main(["--room", "https://www.bilibili.com/video/BV1", "--probe-once"]) == 2
    assert "not a room id" in capsys.readouterr().err


def test_version_flag_exits_cleanly():
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
