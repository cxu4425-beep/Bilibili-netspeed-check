"""The self-test: it has to report a broken machine, not fall over on one."""

from lagscope import selftest
from lagscope.selftest import (
    FAIL, OK, SKIP, WARN, CheckResult, _check, check_dns, check_environment,
    format_report, worst_status,
)


def test_a_check_that_raises_becomes_a_failure_not_a_crash():
    def explode(result):
        raise RuntimeError("the probe blew up")

    result = _check("boom", explode)

    assert result.status == FAIL
    assert any("the probe blew up" in line for line in result.lines)


def test_every_check_is_timed():
    result = _check("quiet", lambda r: None)
    assert result.status == OK
    assert result.lines[-1].endswith("ms)")


def test_the_environment_check_says_what_it_is_running_on():
    result = _check("environment", check_environment)
    body = " ".join(result.lines)
    assert "LagScope" in body and "python" in body


def test_a_resolver_that_answers_nothing_is_a_failure(monkeypatch):
    from lagscope.probes import path as path_module

    monkeypatch.setattr(path_module, "dns_ms", lambda host, **kwargs: None)
    result = _check("dns", check_dns)

    assert result.status == FAIL


def test_the_report_is_readable_and_counts_every_outcome():
    results = [
        CheckResult("fine", OK, ["all good"]),
        CheckResult("iffy", WARN, ["not sure"]),
        CheckResult("broken", FAIL, ["it did not work"]),
        CheckResult("later", SKIP, ["needs a room id"]),
    ]

    report = format_report(results)

    for name in ("fine", "iffy", "broken", "later"):
        assert name in report
    assert "1 ok, 1 warning(s), 1 failure(s), 1 skipped" in report
    assert "[FAIL] broken" in report
    # The privacy note is the promise the output has to keep.
    assert "no public IP" in report


def test_the_worst_outcome_decides_the_exit_code():
    assert worst_status([CheckResult("a", OK)]) == OK
    assert worst_status([CheckResult("a", OK), CheckResult("b", SKIP)]) == SKIP
    assert worst_status([CheckResult("a", SKIP), CheckResult("b", WARN)]) == WARN
    assert worst_status([CheckResult("a", WARN), CheckResult("b", FAIL)]) == FAIL


def test_the_output_never_carries_the_wifi_name():
    """The report is meant to be pasted in public; the SSID is not."""
    report = format_report([CheckResult("path tools", OK, ["default gateway: 192.168.1.1"])])
    assert "ssid" not in report.lower()


def test_a_room_check_without_a_room_is_skipped_not_failed():
    result = _check("room", lambda r: selftest.check_room(r, None, ""))
    assert result.status == SKIP


def test_the_bilibili_checks_report_the_reason_they_could_not_run():
    class Dead:
        def fetch_room_info(self, room):
            raise ConnectionError("Tunnel connection failed: 403 Forbidden")

    result = _check("room", lambda r: selftest.check_room(r, Dead(), "21452505"))

    assert result.status == FAIL
    assert any("403" in line for line in result.lines)
