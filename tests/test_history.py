"""Summarising hours of samples into something small enough to keep."""

import json
import math
import time

import pytest

from lagscope.history import Bucket, History, percentile
from lagscope.models import LatencySample


def _minute_start(offset_minutes=0):
    """A recent, minute-aligned timestamp: buckets outside the window are trimmed."""
    return math.floor(time.time() / 60) * 60 - offset_minutes * 60


def _sample(ts, total, ok=True):
    return LatencySample(ts=ts, total_ms=total, ok=ok, title="room 42")


def test_a_minute_of_samples_becomes_one_row(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    base = _minute_start(10)

    for offset, value in enumerate([100.0, 200.0, 300.0]):
        history.add(_sample(base + offset, value))

    rows = history.buckets()
    assert len(rows) == 1
    row = rows[0]
    assert row.start == base
    assert (row.count, row.ok) == (3, 3)
    assert row.avg_ms == pytest.approx(200.0)
    assert (row.min_ms, row.max_ms) == (100.0, 300.0)
    assert row.jitter_ms == pytest.approx(100.0)
    assert row.label == "room 42"


def test_a_failed_probe_counts_as_loss_not_as_latency(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    base = _minute_start(10)
    history.add(_sample(base, 100.0))
    history.add(LatencySample(ts=base + 1, ok=False, error="boom"))

    row = history.buckets()[0]
    assert (row.count, row.ok) == (2, 1)
    assert row.loss_pct == pytest.approx(50.0)
    assert row.avg_ms == pytest.approx(100.0)   # the failure is not a 0 ms reading


def test_crossing_a_minute_starts_a_new_row(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    base = _minute_start(10)
    history.add(_sample(base, 100.0))
    history.add(_sample(base + 61, 400.0))

    rows = history.buckets()
    assert [row.start for row in rows] == [base, base + 60]
    assert rows[1].avg_ms == pytest.approx(400.0)


def test_events_land_in_the_minute_they_happened(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    history.add(_sample(time.time(), 100.0))
    history.note_event("stall")
    history.note_event("spike")
    history.note_event("nonsense")

    row = history.buckets()[0]
    assert (row.stalls, row.spikes) == (1, 1)


def test_history_survives_a_restart(tmp_path):
    path = tmp_path / "h.json"
    now = time.time()
    history = History(path, bucket_s=60)
    history.add(_sample(now - 120, 100.0))
    history.add(_sample(now - 30, 200.0))
    history.close()

    assert path.exists()
    restored = History(path, bucket_s=60)
    assert [round(row.avg_ms) for row in restored.buckets()] == [100, 200]


def test_rows_older_than_the_retention_window_are_dropped(tmp_path):
    path = tmp_path / "h.json"
    now = time.time()
    rows = [
        Bucket(start=now - 10 * 3600, count=1, ok=1, avg_ms=99.0).as_row(),
        Bucket(start=now - 600, count=1, ok=1, avg_ms=42.0).as_row(),
    ]
    path.write_text(json.dumps({"version": 1, "buckets": rows}), encoding="utf-8")

    history = History(path, bucket_s=60, keep_hours=2)
    assert [row.avg_ms for row in history.buckets()] == [42.0]


def test_a_damaged_file_is_ignored_rather_than_fatal(tmp_path):
    path = tmp_path / "h.json"
    path.write_text("{not json at all", encoding="utf-8")

    history = History(path, bucket_s=60)
    assert history.buckets() == []

    history.add(_sample(time.time(), 100.0))
    history.close()
    assert json.loads(path.read_text(encoding="utf-8"))["buckets"]


def test_rows_that_make_no_sense_are_skipped_but_the_rest_load(tmp_path):
    path = tmp_path / "h.json"
    good = Bucket(start=time.time() - 60, count=1, ok=1, avg_ms=42.0).as_row()
    path.write_text(
        json.dumps({"version": 1, "buckets": ["nonsense", [], good, {"a": 1}]}),
        encoding="utf-8",
    )
    assert [row.avg_ms for row in History(path).buckets()] == [42.0]


def test_summary_weights_each_minute_by_how_many_probes_answered(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    now = time.time()
    # One busy minute at 100 ms, one quiet minute at 500 ms.
    for index in range(9):
        history.add(_sample(now - 120 + index, 100.0))
    history.add(_sample(now - 30, 500.0))

    summary = history.summary(hours=1)
    assert summary["samples"] == 10
    assert summary["avg_ms"] == pytest.approx((9 * 100 + 500) / 10)
    assert summary["max_ms"] == 500.0
    assert summary["loss_pct"] == pytest.approx(0.0)


def test_the_worst_hour_is_the_one_with_the_trouble_in_it(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60, keep_hours=48)
    # Anchored to real hour boundaries: "an hour ago" plus five minutes spills
    # into the next hour whenever this runs near the end of one.
    this_hour = math.floor(time.time() / 3600) * 3600
    quiet_hour = this_hour - 3 * 3600
    bad_hour = this_hour - 3600

    for index in range(5):
        history.add(_sample(quiet_hour + index * 60, 400.0))
    for index in range(5):
        history.add(_sample(bad_hour + index * 60, 120.0))
    history.note_event("stall")        # lands in the minute last written to

    worst = history.worst_hour(hours=6)
    # Higher average, but no stalls, so the quiet hour is not the one to report.
    assert worst["start"] == bad_hour
    assert worst["stalls"] == 1


def test_a_flat_calm_window_has_no_worst_hour_to_name(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    assert history.worst_hour() is None


def test_clearing_empties_both_memory_and_the_file(tmp_path):
    path = tmp_path / "h.json"
    history = History(path, bucket_s=60)
    history.add(_sample(time.time(), 100.0))
    history.close()

    history.clear()
    assert history.buckets() == []
    assert json.loads(path.read_text(encoding="utf-8"))["buckets"] == []


def test_flush_only_writes_when_something_changed(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    assert history.flush() is False
    assert history.flush(force=True) is True


def test_percentile_matches_the_obvious_cases():
    assert percentile([], 95) is None
    assert percentile([5.0], 95) == 5.0
    assert percentile([0.0, 10.0], 50) == pytest.approx(5.0)
    assert percentile([1.0, 2.0, 3.0, 4.0], 100) == 4.0
