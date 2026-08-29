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


def test_report_and_history_flags_have_working_defaults():
    args = build_parser().parse_args(["--report"])
    assert args.report == ""                      # "" means: pick the default filename

    args = build_parser().parse_args(["--history"])
    assert args.history == "24"

    args = build_parser().parse_args(["--report", "out.html", "--history", "all"])
    assert args.report == "out.html" and args.history == "all"


def test_history_window_accepts_hours_or_all():
    from lagscope.cli import _history_hours

    assert _history_hours("24") == 24.0
    assert _history_hours("1.5") == 1.5
    assert _history_hours("all") is None
    assert _history_hours("") == 24.0
    assert _history_hours("nonsense") == 24.0     # never crash on a typo


def test_history_output_says_so_when_nothing_was_recorded(capsys):
    from lagscope.i18n import tr

    assert main(["--history"]) == 0
    assert tr("history.empty") in capsys.readouterr().out


def test_report_writes_a_page_even_with_an_empty_history(tmp_path, capsys):
    target = tmp_path / "report.html"
    assert main(["--report", str(target)]) == 0

    document = target.read_text(encoding="utf-8")
    assert document.startswith("<!doctype html>")
    assert str(target) in capsys.readouterr().out
