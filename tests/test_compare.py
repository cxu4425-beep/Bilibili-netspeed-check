"""Marking a moment, and answering "did the change help?" honestly.

The interesting part is refusing to answer. A comparison that quietly uses six
hours of "before" against five minutes of "after" will call almost anything an
improvement, so most of these tests are about the cases where it declines.
"""

import json
import math
import time

import pytest

from lagscope.history import MAX_COMPARE_SPAN_S, MAX_MARKERS, History
from lagscope.i18n import tr
from lagscope.models import LatencySample
from lagscope.report import build_html, build_text, comparison_rows


def _minute(offset_minutes=0):
    return math.floor(time.time() / 60) * 60 - offset_minutes * 60


def _fill(history, start, minutes, value):
    """One sample a minute at a steady latency."""
    for index in range(minutes):
        history.add(LatencySample(ts=start + index * 60, total_ms=value, ok=True))


# ------------------------------------------------------------------ markers
def test_a_marker_is_kept_and_survives_a_restart(tmp_path):
    path = tmp_path / "h.json"
    history = History(path, bucket_s=60)
    _fill(history, _minute(20), 20, 100.0)
    history.mark("changed to 5GHz", ts=_minute(10))
    history.close()

    restored = History(path, bucket_s=60)
    assert [entry["label"] for entry in restored.markers()] == ["changed to 5GHz"]


def test_markers_stay_in_order_and_bounded(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    for index in range(MAX_MARKERS + 10):
        history.mark(f"change {index}", ts=_minute(200 - index))

    markers = history.markers()
    assert len(markers) == MAX_MARKERS
    assert markers == sorted(markers, key=lambda entry: entry["ts"])


def test_a_damaged_marker_does_not_stop_the_rest_loading(tmp_path):
    path = tmp_path / "h.json"
    good = {"ts": _minute(5), "label": "fine"}
    path.write_text(json.dumps({"version": 1, "buckets": [],
                                "markers": ["nonsense", {"no": "ts"}, good]}),
                    encoding="utf-8")

    assert [entry["label"] for entry in History(path).markers()] == ["fine"]


# --------------------------------------------------------------- comparison
def test_an_improvement_is_measured_either_side_of_the_marker(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    marker = _minute(30)
    _fill(history, _minute(60), 30, 200.0)        # before: 200 ms
    _fill(history, marker, 30, 80.0)              # after: 80 ms

    compare = history.compare(marker)

    assert compare is not None
    assert compare["before"]["avg_ms"] == pytest.approx(200.0)
    assert compare["after"]["avg_ms"] == pytest.approx(80.0)
    assert compare["delta_ms"] == pytest.approx(-120.0)


def test_the_two_sides_always_use_the_same_span(tmp_path):
    """Six hours of before against ten minutes of after is not a comparison."""
    history = History(tmp_path / "h.json", bucket_s=60)
    marker = _minute(10)
    _fill(history, _minute(190), 180, 200.0)      # three hours before
    _fill(history, marker, 10, 80.0)              # ten minutes after

    compare = history.compare(marker)

    assert compare is not None
    assert compare["span_s"] == pytest.approx(600, abs=60)   # the shorter side wins
    assert compare["before"]["buckets"] == compare["after"]["buckets"]


def test_the_span_is_capped_so_before_cannot_span_a_different_evening(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60, keep_hours=48)
    marker = _minute(12 * 60)
    _fill(history, _minute(24 * 60), 12 * 60, 200.0)
    _fill(history, marker, 12 * 60, 80.0)

    compare = history.compare(marker)

    assert compare is not None
    assert compare["span_s"] == pytest.approx(MAX_COMPARE_SPAN_S)


def test_too_little_data_on_one_side_declines_to_answer(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    marker = _minute(2)
    _fill(history, _minute(60), 58, 200.0)
    _fill(history, marker, 2, 80.0)               # only two minutes after

    assert history.compare(marker) is None


def test_a_marker_with_no_history_at_all_declines(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    assert history.compare(_minute(5)) is None


def test_loss_and_p95_are_compared_too(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    marker = _minute(20)
    for index in range(20):                       # before: every other probe fails
        ts = _minute(40) + index * 60
        history.add(LatencySample(ts=ts, total_ms=300.0, ok=True))
        history.add(LatencySample(ts=ts + 1, ok=False, error="boom"))
    _fill(history, marker, 20, 100.0)             # after: all fine

    compare = history.compare(marker)

    assert compare["before"]["loss_pct"] == pytest.approx(50.0)
    assert compare["after"]["loss_pct"] == pytest.approx(0.0)
    assert compare["delta_loss_pct"] == pytest.approx(-50.0)
    assert compare["delta_p95_ms"] is not None and compare["delta_p95_ms"] < 0


# ------------------------------------------------------------------ wording
def _entry(before_ms, after_ms, label="changed the DNS"):
    history_span = 900.0
    return {"label": label, "compare": {
        "ts": _minute(15), "span_s": history_span,
        "before": {"avg_ms": before_ms, "p95_ms": before_ms, "loss_pct": 0.0,
                   "buckets": 15, "samples": 15, "stalls": 0, "spikes": 0},
        "after": {"avg_ms": after_ms, "p95_ms": after_ms, "loss_pct": 0.0,
                  "buckets": 15, "samples": 15, "stalls": 0, "spikes": 0},
        "delta_ms": None if (before_ms is None or after_ms is None) else after_ms - before_ms,
    }}


def test_a_real_improvement_is_called_one():
    rows = comparison_rows([_entry(200.0, 80.0)])
    assert tr("compare.better", value="120 ms") == rows[0][3]


def test_a_regression_is_not_dressed_up():
    rows = comparison_rows([_entry(80.0, 200.0)])
    assert rows[0][3] == tr("compare.worse", value="120 ms")


def test_a_few_milliseconds_either_way_is_no_difference():
    assert comparison_rows([_entry(100.0, 104.0)])[0][3] == tr("compare.same")
    assert comparison_rows([_entry(100.0, 96.0)])[0][3] == tr("compare.same")


def test_a_missing_side_says_so_rather_than_guessing():
    assert comparison_rows([_entry(100.0, None)])[0][3] == tr("compare.unclear")


def test_an_entry_still_collecting_its_after_is_left_out():
    assert comparison_rows([{"label": "just now", "compare": None}]) == []


def test_the_span_is_stated_in_readable_units():
    rows = comparison_rows([_entry(200.0, 80.0)])
    assert rows[0][4] == tr("compare.span_min", n=15)


# ------------------------------------------------------------------- report
def test_the_report_carries_the_comparison(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    entries = [_entry(200.0, 80.0, label="moved the router")]

    document = build_html(buckets=[], summary=history.summary(24.0), comparisons=entries)
    text = build_text(summary=history.summary(24.0), comparisons=entries)

    assert tr("compare.title") in document and "moved the router" in document
    assert tr("compare.title") in text and "moved the router" in text


def test_no_markers_means_no_section(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    document = build_html(buckets=[], summary=history.summary(24.0), comparisons=[])
    assert tr("compare.title") not in document


def test_a_hostile_label_cannot_inject_markup(tmp_path):
    history = History(tmp_path / "h.json", bucket_s=60)
    entries = [_entry(200.0, 80.0, label="<script>alert(1)</script>")]

    document = build_html(buckets=[], summary=history.summary(24.0), comparisons=entries)

    assert "<script>" not in document
    assert "&lt;script&gt;" in document
