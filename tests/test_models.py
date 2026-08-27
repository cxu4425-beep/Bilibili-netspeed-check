from bili_latency.models import LatencySample, RollingStats


def _stats(values, maxlen=100):
    stats = RollingStats(maxlen)
    for value in values:
        stats.append(LatencySample(total_ms=value, ok=value is not None))
    return stats


def test_basic_statistics():
    stats = _stats([100, 200, 300, 400])
    assert stats.avg() == 250
    assert stats.minimum() == 100
    assert stats.maximum() == 400
    assert stats.percentile(50) == 250
    assert stats.jitter() == 100


def test_failed_samples_are_excluded_from_values_but_counted():
    stats = _stats([100, None, 300])
    assert stats.avg() == 200
    assert stats.failure_rate() == 1 / 3
    assert stats.spark_values(3) == [100, None, 300]


def test_window_is_bounded():
    stats = _stats(range(500), maxlen=50)
    assert len(stats) == 50
    assert stats.minimum() == 450


def test_resize_keeps_recent_samples():
    stats = _stats(range(30))
    stats.resize(10)
    assert len(stats) == 10
    assert stats.minimum() == 20


def test_empty_window_returns_none():
    stats = RollingStats(10)
    assert stats.avg() is None
    assert stats.percentile(95) is None
    assert stats.jitter() is None
    assert stats.failure_rate() == 0.0
