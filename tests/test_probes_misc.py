import pytest

from lagscope.probes.display import DisplayProbe
from lagscope.probes.network import clock_offset_ms, host_port_from_url, tcp_rtt_ms


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://cdn.example.com/live/1.m3u8", ("cdn.example.com", 443)),
        ("http://cdn.example.com/live/1.flv", ("cdn.example.com", 80)),
        ("https://cdn.example.com:8443/live/1.m3u8", ("cdn.example.com", 8443)),
        ("garbage", ("", 443)),
    ],
)
def test_host_port_from_url(url, expected):
    assert host_port_from_url(url) == expected


def test_clock_offset_from_http_date():
    # Server says 09:00:00, we received it at 09:00:04 with a 40 ms round trip.
    offset = clock_offset_ms("Thu, 27 Aug 2026 09:00:00 GMT", 1787821204.0, 40.0)
    assert offset == pytest.approx(-4000 + 20, abs=1)


def test_clock_offset_handles_a_missing_or_broken_header():
    assert clock_offset_ms("", 1787821204.0, 10.0) is None
    assert clock_offset_ms("not a date", 1787821204.0, 10.0) is None


def test_tcp_rtt_returns_none_when_unreachable():
    assert tcp_rtt_ms("", 443, 0.2) is None
    # Port 9 (discard) on the loopback address is closed in CI containers.
    assert tcp_rtt_ms("127.0.0.1", 9, 0.2) is None


def test_display_probe_uses_the_median_frame_interval():
    probe = DisplayProbe()
    timestamp = 0.0
    for _ in range(40):
        timestamp += 1 / 60
        probe.record_frame(timestamp)
    assert probe.frame_ms == pytest.approx(16.67, abs=0.1)
    assert probe.estimate_ms(frames_in_flight=2) == pytest.approx(33.3, abs=0.5)
    assert probe.estimate_ms(frames_in_flight=2, manual_offset_ms=10) == pytest.approx(43.3, abs=0.5)


def test_display_probe_ignores_stalls_while_hidden():
    probe = DisplayProbe()
    timestamp = 0.0
    for _ in range(10):
        timestamp += 1 / 60
        probe.record_frame(timestamp)
    probe.record_frame(timestamp + 30.0)  # window was occluded for 30 s
    assert probe.frame_ms == pytest.approx(16.67, abs=0.1)


def test_display_probe_falls_back_to_the_refresh_rate():
    probe = DisplayProbe()
    assert probe.frame_ms is None
    probe.refresh_hz = 144.0
    assert probe.frame_period_ms() == pytest.approx(6.94, abs=0.01)
    assert probe.snapshot()["display_ms"] == pytest.approx(13.9, abs=0.1)


def test_display_probe_reset_and_loop_lag():
    probe = DisplayProbe()
    probe.record_loop_lag(4.0)
    probe.record_loop_lag(6.0)
    assert probe.loop_lag_ms == pytest.approx(5.0)
    probe.record_loop_lag(-1.0)  # ignored
    probe.reset()
    assert probe.loop_lag_ms is None
