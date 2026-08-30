"""The exported report: self-contained, honest about gaps, safe to share."""

import math
import re
import time

from lagscope import report
from lagscope.history import Bucket, History
from lagscope.i18n import set_language, tr
from lagscope.models import ExtraResult, LatencySample
from lagscope.probes.path import PathReport, PingStats, WifiInfo
from lagscope.report import (
    build_html, build_text, chart_svg, default_report_path, grid_values, nice_ceiling,
    write_report,
)


def _history(tmp_path, minutes=30, value=120.0):
    history = History(tmp_path / "h.json", bucket_s=60)
    base = math.floor(time.time() / 60) * 60 - minutes * 60
    for index in range(minutes):
        for offset in (0, 20, 40):
            history.add(LatencySample(ts=base + index * 60 + offset,
                                      total_ms=value + index, ok=True, title="room 42"))
    return history


def _path_report():
    return PathReport(
        target="8.8.8.8",
        gateway="192.168.1.1",
        gateway_stats=PingStats(host="192.168.1.1", sent=5, received=5, avg_ms=2.0),
        hop_stats=PingStats(host="100.64.0.1", sent=5, received=5, avg_ms=11.0),
        target_stats=PingStats(host="8.8.8.8", sent=5, received=4, avg_ms=30.0),
        wifi=WifiInfo(ssid="家里的路由器", signal_pct=42, radio="802.11n"),
    )


# ------------------------------------------------------------------- chart
def test_an_empty_history_still_renders_something(tmp_path):
    svg = chart_svg([], 60.0)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert tr("report.no_data") in svg


def test_the_line_breaks_across_a_gap_rather_than_inventing_data():
    now = math.floor(time.time() / 60) * 60
    rows = [
        Bucket(start=now - 600, count=1, ok=1, avg_ms=100.0, min_ms=90.0, max_ms=110.0),
        Bucket(start=now - 540, count=1, ok=1, avg_ms=100.0, min_ms=90.0, max_ms=110.0),
        # ...an hour with the computer asleep...
        Bucket(start=now - 60, count=1, ok=1, avg_ms=100.0, min_ms=90.0, max_ms=110.0),
    ]
    svg = chart_svg(rows, 60.0)
    assert svg.count("<polyline") == 2      # two runs, not one line across the gap


def test_stalls_are_marked_on_the_chart():
    now = math.floor(time.time() / 60) * 60
    calm = [Bucket(start=now - 120, count=1, ok=1, avg_ms=100.0, min_ms=100.0, max_ms=100.0)]
    rough = calm + [Bucket(start=now - 60, count=1, ok=0, avg_ms=100.0, min_ms=100.0,
                           max_ms=100.0, stalls=2)]
    assert chart_svg(rough, 60.0).count("<rect") > chart_svg(calm, 60.0).count("<rect")


def test_the_scale_top_is_a_number_a_person_would_pick():
    assert nice_ceiling(0) == 1.0
    assert nice_ceiling(83.0) == 100.0
    assert nice_ceiling(1100.0) == 1500.0
    assert nice_ceiling(2400.0) == 2500.0


def test_gridlines_are_labelled_with_round_numbers():
    # Quartering 750 would print 187.5 ms; a rounded step prints 200 / 400 / 600.
    assert grid_values(750.0) == [0.0, 200.0, 400.0, 600.0, 750.0]
    assert grid_values(100.0) == [0.0, 25.0, 50.0, 75.0, 100.0]
    assert grid_values(0.0) == [0.0]


def test_text_inside_the_chart_is_escaped():
    rows = [Bucket(start=time.time() - 60, count=1, ok=1, avg_ms=1.0,
                   min_ms=1.0, max_ms=1.0, label="<script>x</script>")]
    assert "<script>" not in chart_svg(rows, 60.0)


# ------------------------------------------------------------------ report
def test_the_page_carries_everything_it_needs_to_render(tmp_path):
    history = _history(tmp_path)
    document = build_html(
        buckets=history.buckets(24.0), summary=history.summary(24.0),
        worst=history.worst_hour(24.0), path_report=_path_report(),
        verdict_key="verdict.wifi", good_ms=200.0, warn_ms=500.0,
    )

    assert document.startswith("<!doctype html>")
    assert "<svg" in document                       # the chart is inline
    # Nothing is fetched when the file is opened: no scripts, no external assets.
    assert "<script" not in document.lower()
    assert not re.search(r'(src|href)\s*=\s*"(?!https://github)', document)
    assert "@import" not in document


def test_the_findings_are_actually_in_the_page(tmp_path):
    history = _history(tmp_path)
    document = build_html(
        buckets=history.buckets(24.0), summary=history.summary(24.0),
        worst=history.worst_hour(24.0), path_report=_path_report(),
        verdict_key="verdict.wifi", verdict_detail="gateway",
        target_label="room 42",
    )

    assert "192.168.1.1" in document and "8.8.8.8" in document
    assert tr("verdict.wifi") in document
    assert "room 42" in document
    assert tr("report.privacy") in document


def test_a_report_with_no_history_is_still_a_valid_page(tmp_path):
    history = History(tmp_path / "h.json")
    document = build_html(buckets=[], summary=history.summary(24.0))

    assert document.startswith("<!doctype html>")
    assert tr("report.no_data") in document


def test_a_hostile_label_cannot_inject_markup(tmp_path):
    history = _history(tmp_path)
    document = build_html(
        buckets=history.buckets(24.0), summary=history.summary(24.0),
        target_label='<img src=x onerror="alert(1)">',
        extras=[ExtraResult(key="a", label="<b>bold</b>", ident="1.2.3.4",
                            rtt_ms=5.0, ok=True)],
    )

    # The text survives, but only ever as text: no live tag reaches the page.
    assert "<img" not in document
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in document
    assert "<b>bold</b>" not in document
    assert "&lt;b&gt;bold&lt;/b&gt;" in document


def test_extras_appear_with_their_own_numbers(tmp_path):
    history = _history(tmp_path)
    document = build_html(
        buckets=history.buckets(24.0), summary=history.summary(24.0),
        extras=[
            ExtraResult(key="a", label="路由器", ident="192.168.1.1", rtt_ms=2.0, ok=True),
            ExtraResult(key="b", label="Discord", ident="Discord.exe", ok=False),
        ],
    )
    assert "路由器" in document and "Discord.exe" in document
    assert tr("report.extras") in document


# -------------------------------------------------------------------- text
def test_the_text_version_is_pasteable_and_carries_the_verdict(tmp_path):
    history = _history(tmp_path)
    text = build_text(
        summary=history.summary(24.0), worst=history.worst_hour(24.0),
        path_report=_path_report(), verdict_key="verdict.isp", target_label="room 42",
    )

    assert "<" not in text                       # no markup: it goes into a forum post
    assert tr("verdict.isp") in text
    assert tr("diag.you_router") in text
    assert "room 42" in text


def test_a_calm_window_says_so_instead_of_naming_an_hour(tmp_path):
    history = History(tmp_path / "h.json")
    text = build_text(summary=history.summary(24.0), worst=None)
    assert tr("report.no_trouble") in text


# ------------------------------------------------------------------ writing
def test_writing_creates_the_folder_and_returns_the_path(tmp_path):
    target = tmp_path / "nested" / "report.html"
    written = write_report("<!doctype html><html></html>", target)

    assert written == target
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_the_default_name_is_unique_per_second_and_lands_in_the_config_dir():
    first = default_report_path(1_700_000_000.0)
    later = default_report_path(1_700_000_060.0)

    assert first.suffix == ".html" and first.parent.name == "reports"
    assert first != later


def test_the_report_follows_the_interface_language(tmp_path):
    history = _history(tmp_path)
    try:
        set_language("en")
        english = build_html(buckets=history.buckets(24.0), summary=history.summary(24.0))
        set_language("zh_TW")
        chinese = build_html(buckets=history.buckets(24.0), summary=history.summary(24.0))
    finally:
        set_language("zh_CN")

    assert "Connection health report" in english
    assert "網路體檢報告" in chinese


def test_the_pasteable_table_lines_up_with_wide_glyphs(tmp_path):
    """CJK labels are two columns wide; padding by character count looks ragged."""
    set_language("zh_CN")
    history = _history(tmp_path)
    text = build_text(summary=history.summary(24.0), worst=history.worst_hour(24.0))

    columns = set()
    for line in text.splitlines():
        match = re.match(r"^ {2}(\S.*?)\s{2,}(\S.*)$", line)
        if match:
            # Where the value starts, counted in monospaced columns.
            columns.add(report._width(line) - report._width(match.group(2)))

    # Every value begins in the same column, whatever its label was made of.
    assert len(columns) == 1


def test_the_chart_does_not_depend_on_the_order_buckets_arrive_in():
    """Recorded history is ordered; a chart that quietly misdraws when it is
    not would hide the problem rather than show it."""
    import time

    from lagscope.history import Bucket
    from lagscope.report import chart_svg

    now = time.time()
    ordered = [Bucket(start=now - (60 - i) * 60, count=20, ok=20,
                      avg_ms=60 + (i % 20) * 3, min_ms=50, max_ms=140, p95_ms=120)
               for i in range(60)]
    shuffled = ordered[30:] + ordered[:30]

    assert chart_svg(ordered, 60.0, None, None, []) == \
        chart_svg(shuffled, 60.0, None, None, [])
