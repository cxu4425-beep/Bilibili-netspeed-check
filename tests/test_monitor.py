"""The rules that decide what ends up in a sample (no Qt event loop needed)."""

import pytest

from bili_latency.config import Config
from bili_latency.models import NetworkMeasurement, StreamMeasurement
from bili_latency.monitor import STATUS_ERROR, STATUS_NO_ROOM, STATUS_OFFLINE, STATUS_OK, MonitorWorker


class FakeClient:
    def __init__(self):
        self.timeout_s = 4.0

    def measure(self, url, rtt_ms=None):
        return NetworkMeasurement(rtt_ms=30.0, ttfb_ms=40.0, host="api", clock_offset_ms=12.0)

    def recycle(self):
        pass

    def close(self):
        pass


class FakeStream:
    def __init__(self, measurement, rtt_ms=45.0):
        self.measurement = measurement
        self.rtt_ms = rtt_ms
        self.room_info = None
        self.clock_offset_ms = None

    def measure(self, room_id=None):
        return self.measurement

    def endpoint_rtt_ms(self, timeout_s=4.0):
        return self.rtt_ms

    def set_clock_offset_ms(self, offset):
        self.clock_offset_ms = offset

    def set_room(self, room_id):
        pass


def _worker(config, measurement=None, rtt_ms=45.0):
    worker = MonitorWorker(config)
    worker._client = FakeClient()
    worker._stream = FakeStream(measurement, rtt_ms)
    return worker


def _config(**kwargs):
    config = Config()
    config.room_id = kwargs.get("room_id", "123")
    config.display.include_in_total = kwargs.get("include_display", True)
    return config.sanitized()


def test_total_is_stream_plus_display_without_double_counting_the_network():
    measurement = StreamMeasurement(stream_ms=2500.0, method="hls-pdt", estimated=False,
                                    edge_lag_ms=2000.0, buffer_ms=480.0, host="cdn")
    worker = _worker(_config(), measurement)
    worker.setDisplayLatency(33.0)

    sample = worker._run_round()

    assert sample.ok and sample.estimated is False
    assert sample.stream_ms == 2500.0
    assert sample.network_ms == 45.0        # reported, not added
    assert sample.total_ms == pytest.approx(2533.0)
    assert sample.method == "hls-pdt"


def test_display_can_be_left_out_of_the_total():
    measurement = StreamMeasurement(stream_ms=2500.0, method="hls-pdt", estimated=False)
    worker = _worker(_config(include_display=False), measurement)
    worker.setDisplayLatency(33.0)

    sample = worker._run_round()

    assert sample.display_ms == 33.0        # still shown in the breakdown
    assert sample.total_ms == pytest.approx(2500.0)


def test_network_only_mode_without_a_room(monkeypatch):
    monkeypatch.setattr("bili_latency.monitor.tcp_rtt_ms", lambda *a, **k: 21.0)
    worker = _worker(_config(room_id=""), None, rtt_ms=None)
    worker.setDisplayLatency(16.0)

    sample = worker._run_round()

    assert sample.method == "network-only"
    assert sample.ok and sample.total_ms == pytest.approx(37.0)
    assert worker._last_status == STATUS_NO_ROOM


def test_network_only_mode_marks_an_unreachable_network(monkeypatch):
    monkeypatch.setattr("bili_latency.monitor.tcp_rtt_ms", lambda *a, **k: None)
    worker = _worker(_config(room_id=""), None, rtt_ms=None)

    sample = worker._run_round()

    assert not sample.ok and sample.total_ms is None
    assert worker._last_status == STATUS_ERROR


def test_an_offline_room_is_reported_as_offline_not_as_an_error():
    worker = _worker(_config(), StreamMeasurement(stream_ms=None, method="none", error="offline"))

    sample = worker._run_round()

    assert not sample.ok and sample.total_ms is None
    assert worker._last_status == STATUS_OFFLINE


def test_a_failed_probe_keeps_the_network_reading():
    worker = _worker(_config(), StreamMeasurement(stream_ms=None, method="none", error="timeout"))

    sample = worker._run_round()

    assert not sample.ok
    assert sample.network_ms == 45.0
    assert sample.error == "timeout"
    assert worker._last_status == STATUS_ERROR


def test_clock_offset_is_handed_to_the_stream_probe():
    worker = _worker(_config(), StreamMeasurement(stream_ms=1000.0, method="hls-pdt", estimated=False))
    worker._run_round()
    assert worker._stream.clock_offset_ms == 12.0
    assert worker._last_status == STATUS_OK


def test_clock_sync_is_rate_limited():
    worker = _worker(_config(), StreamMeasurement(stream_ms=1000.0, method="hls-pdt"))
    worker._run_round()
    worker._stream.clock_offset_ms = None
    worker._run_round()                     # second round is inside the window
    assert worker._stream.clock_offset_ms is None
