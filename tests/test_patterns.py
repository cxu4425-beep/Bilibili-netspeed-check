"""Grouping history by edge and by hour, and the action list built from it.

The risk in a feature like this is not that it fails to find a pattern - it is
that it finds one in noise and someone spends a Saturday acting on it. So the
tests that carry the most weight are the ones proving it declines: too little
data, a difference too small to matter, an hour that is only barely worse.
"""

import time

import pytest

from lagscope.actions import (
    PRIORITY_BLOCKING, has_local_cause, suggest,
)
from lagscope.history import Bucket
from lagscope.patterns import (
    EDGE_DIFFERENCE_MS, MIN_BUCKETS_PER_EDGE, PERIOD_DIFFERENCE_MS,
    by_edge, by_period, edge_verdict, hour_ranges,
)

GOOD = "upos-sz-mirrorhw.bilivideo.com"
BAD = "cn-hbyc-ct-01.bilivideo.com"
PEER = "xy118x123x45x67xy.mcdn.bilivideo.cn"


def rows(host, count, avg_ms, start=None, stalls=0, ok=20):
    base = start if start is not None else time.time() - count * 60
    return [Bucket(start=base + i * 60, count=20, ok=ok, avg_ms=avg_ms,
                   p95_ms=avg_ms + 40, stalls=stalls, host=host)
            for i in range(count)]


# ------------------------------------------------------------- grouping
def test_minutes_are_grouped_by_the_edge_that_served_them():
    stats = by_edge(rows(GOOD, 20, 60) + rows(BAD, 30, 180))
    hosts = {item.host: item for item in stats}

    assert hosts[GOOD].avg_ms == pytest.approx(60)
    assert hosts[BAD].avg_ms == pytest.approx(180)
    assert hosts[GOOD].share_pct == pytest.approx(40.0)
    assert hosts[BAD].share_pct == pytest.approx(60.0)


def test_minutes_with_no_edge_recorded_are_left_out_not_lumped_together():
    """History written before edges were kept must not become a fake edge."""
    old = [Bucket(start=time.time() - i * 60, count=20, ok=20, avg_ms=90)
           for i in range(30)]
    assert by_edge(old) == []
    assert len(by_edge(old + rows(GOOD, 15, 60))) == 1


def test_the_fastest_edge_is_listed_first():
    stats = by_edge(rows(BAD, 20, 180) + rows(GOOD, 20, 60))
    assert stats[0].host == GOOD


def test_loss_is_computed_per_edge():
    stats = by_edge(rows(BAD, 20, 180, ok=18))
    assert stats[0].loss_pct == pytest.approx(10.0)


# -------------------------------------------------------------- verdict
def test_a_real_difference_between_edges_is_reported():
    verdict = edge_verdict(by_edge(rows(GOOD, 20, 60) + rows(BAD, 30, 180)))
    assert verdict.matters
    assert verdict.best.host == GOOD and verdict.worst.host == BAD
    assert verdict.difference_ms == pytest.approx(120)


def test_the_edge_that_costs_the_most_time_wins_not_the_slowest_one():
    """A dreadful edge you were on briefly matters less than a mediocre one
    you were parked on all evening, and the advice should follow the harm."""
    stats = by_edge(rows(GOOD, 20, 60) + rows(BAD, 60, 150) + rows(PEER, 5, 400))
    verdict = edge_verdict(stats)

    assert verdict.worst.host == BAD           # not PEER, despite PEER being slower
    assert verdict.worst.share_pct > 50


def test_edges_that_perform_alike_are_not_dressed_up_as_a_finding():
    verdict = edge_verdict(by_edge(rows(GOOD, 20, 60) + rows(BAD, 20, 66)))
    assert not verdict.matters
    assert verdict.key == "edge.same"


def test_a_difference_just_under_the_threshold_is_not_reported():
    small = EDGE_DIFFERENCE_MS - 1
    verdict = edge_verdict(by_edge(rows(GOOD, 20, 60) + rows(BAD, 20, 60 + small)))
    assert verdict.key == "edge.same"


def test_an_edge_seen_only_briefly_is_not_evidence_about_that_edge():
    stats = by_edge(rows(GOOD, 30, 60) + rows(BAD, MIN_BUCKETS_PER_EDGE - 1, 300))
    verdict = edge_verdict(stats)
    assert verdict.key == "edge.only_one"      # the brief one does not qualify


def test_one_edge_all_along_says_there_is_nothing_to_compare():
    assert edge_verdict(by_edge(rows(GOOD, 30, 60))).key == "edge.only_one"


def test_no_data_says_so_rather_than_concluding():
    assert edge_verdict(by_edge([])).key == "edge.not_enough"
    assert edge_verdict([]).key == "edge.not_enough"


# -------------------------------------------------------------- periods
def _at_hour(hour, count, avg_ms, days=3):
    """Buckets landing in a given local hour, across several days."""
    out = []
    for day in range(days):
        anchor = time.time() - day * 86400
        stamp = time.localtime(anchor)
        midnight = anchor - stamp.tm_hour * 3600 - stamp.tm_min * 60 - stamp.tm_sec
        for i in range(count):
            out.append(Bucket(start=midnight + hour * 3600 + i * 60,
                              count=20, ok=20, avg_ms=avg_ms, host=GOOD))
    return out


def test_a_bad_hour_is_found_when_it_is_really_bad():
    data = _at_hour(21, 40, 260) + _at_hour(10, 40, 60) + _at_hour(15, 40, 65)
    report = by_period(data)

    assert report.has_pattern
    assert report.worst.hour == 21
    assert 21 in report.worst_hours


def test_a_flat_day_is_reported_as_having_no_pattern():
    """Saying "no pattern" rules out a whole family of causes; it is an answer."""
    data = _at_hour(21, 40, 100) + _at_hour(10, 40, 98) + _at_hour(15, 40, 102)
    assert by_period(data).key == "pattern.none"


def test_an_hour_barely_worse_than_the_rest_is_not_called_the_bad_hour():
    small = PERIOD_DIFFERENCE_MS - 5
    data = _at_hour(21, 40, 100 + small) + _at_hour(10, 40, 100) + _at_hour(15, 40, 100)
    assert by_period(data).key == "pattern.none"


def test_an_hour_with_too_few_minutes_is_not_ranked():
    data = _at_hour(21, 3, 400, days=1) + _at_hour(10, 40, 60)
    report = by_period(data)
    assert report.key in ("pattern.none", "pattern.not_enough")
    assert report.worst is None or report.worst.hour != 21


def test_nothing_recorded_says_so():
    assert by_period([]).key == "pattern.no_data"


@pytest.mark.parametrize(
    "hours,expected",
    [
        ([21, 22, 23], [(21, 23)]),
        ([21, 22, 23, 9], [(9, 9), (21, 23)]),
        ([1], [(1, 1)]),
        ([], []),
        ([5, 5, 6], [(5, 6)]),
    ],
)
def test_consecutive_hours_read_as_a_range(hours, expected):
    assert hour_ranges(hours) == expected


# -------------------------------------------------------------- actions
def test_nothing_measured_produces_no_advice():
    """A list that always says something teaches people to ignore the list."""
    assert suggest() == []


def test_a_peer_node_earns_a_specific_suggestion():
    actions = suggest(peer_hosts=[PEER])
    assert actions[0].key == "action.peer_node"
    assert PEER in actions[0].detail


def test_packet_loss_outranks_everything_else():
    actions = suggest(loss_pct=4.0, pattern=None,
                      edge_verdict=edge_verdict(by_edge(rows(GOOD, 20, 60) + rows(BAD, 30, 200))))
    assert actions[0].key == "action.loss"
    assert actions[0].priority == PRIORITY_BLOCKING


def test_ordinary_loss_does_not_trigger_the_loss_warning():
    assert not any(a.key == "action.loss" for a in suggest(loss_pct=0.3))


def test_the_path_verdict_becomes_an_action():
    assert any(a.key == "action.wifi" for a in suggest(verdict_key="verdict.wifi"))
    assert any(a.key == "action.isp" for a in suggest(verdict_key="verdict.isp"))


def test_an_unknown_verdict_produces_no_action_rather_than_a_guess():
    assert suggest(verdict_key="verdict.unknown") == []


def test_a_fast_line_is_not_told_to_lower_the_quality():
    assert not any(a.key == "action.lower_quality" for a in suggest(speed_mbps=94.0))
    assert any(a.key == "action.lower_quality" for a in suggest(speed_mbps=2.0))


def test_advice_that_is_all_congestion_is_marked_as_not_yours_to_fix():
    congestion_only = suggest(verdict_key="verdict.isp")
    assert not has_local_cause(congestion_only)

    with_local = suggest(verdict_key="verdict.wifi")
    assert has_local_cause(with_local)


def test_loss_is_not_suggested_twice_when_the_verdict_already_blamed_it():
    actions = suggest(verdict_key="verdict.loss", loss_pct=9.0)
    assert [a.key for a in actions].count("action.loss") == 1


def test_only_persistent_flapping_is_worth_mentioning():
    assert not any(a.key == "action.flapping" for a in suggest(switches=2))
    assert any(a.key == "action.flapping" for a in suggest(switches=8))
