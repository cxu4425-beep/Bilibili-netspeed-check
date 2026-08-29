"""Moving to a faster CDN edge - and, more often, deciding not to.

The interesting behaviour here is the restraint: an edge swap reconnects the
stream, so the bar to clear is deliberately high and the cooldown deliberately
long. Most of these tests are about the cases where nothing should happen.
"""

import time

import pytest

from lagscope.probes.stream import (
    SWITCH_COOLDOWN_S, CdnLine, StreamEndpoint, StreamProbe,
)


def _endpoint(host, fmt="fmp4"):
    return StreamEndpoint(url=f"https://{host}/live/stream.m3u8",
                          protocol="http_hls", fmt=fmt)


def _probe(hosts, auto_cdn=True):
    probe = StreamProbe(client=None, auto_cdn=auto_cdn)
    probe._endpoints = [_endpoint(host) for host in hosts]
    return probe


def _lines(*pairs):
    """(host, rtt) pairs as the sorted list compare_lines produces."""
    lines = [CdnLine(host=host, rtt_ms=rtt) for host, rtt in pairs]
    reachable = sorted((line for line in lines if line.reachable),
                       key=lambda line: line.rtt_ms)
    return reachable + [line for line in lines if not line.reachable]


# --------------------------------------------------------------- switching
def test_a_clearly_faster_edge_is_taken():
    probe = _probe(["slow.example", "fast.example"])
    assert probe.current_host == "slow.example"

    switch = probe.consider_switch(_lines(("slow.example", 180.0), ("fast.example", 40.0)))

    assert switch is not None
    assert (switch.from_host, switch.to_host) == ("slow.example", "fast.example")
    assert switch.saved_ms == pytest.approx(140.0)
    assert probe.current_host == "fast.example"


def test_a_marginally_faster_edge_is_left_alone():
    """4 ms off 20 ms is noise; reconnecting the stream for it is not a win."""
    probe = _probe(["a.example", "b.example"])
    assert probe.consider_switch(_lines(("a.example", 20.0), ("b.example", 16.0))) is None
    assert probe.current_host == "a.example"


def test_a_big_absolute_gain_that_is_a_small_proportion_is_left_alone():
    # 30 ms off 500 ms clears the absolute margin but is only 6% - the kind of
    # difference that comes back on the next measurement.
    probe = _probe(["a.example", "b.example"])
    assert probe.consider_switch(_lines(("a.example", 500.0), ("b.example", 470.0))) is None


def test_a_big_proportional_gain_that_is_a_small_absolute_one_is_left_alone():
    # Half of 8 ms is still only 4 ms, and both edges are already close.
    probe = _probe(["a.example", "b.example"])
    assert probe.consider_switch(_lines(("a.example", 8.0), ("b.example", 4.0))) is None


def test_an_edge_that_stopped_answering_is_abandoned_without_haggling():
    probe = _probe(["dead.example", "alive.example"])
    switch = probe.consider_switch(_lines(("dead.example", None), ("alive.example", 90.0)))

    assert switch is not None and switch.to_host == "alive.example"
    assert switch.saved_ms is None          # nothing to compare against


def test_already_on_the_fastest_edge_is_not_a_switch():
    probe = _probe(["fast.example", "slow.example"])
    assert probe.consider_switch(_lines(("fast.example", 20.0), ("slow.example", 200.0))) is None
    # ...but the choice is remembered, so a refreshed endpoint list keeps it.
    assert probe.preferred_host == "fast.example"


def test_nothing_happens_without_measurements():
    probe = _probe(["a.example", "b.example"])
    assert probe.consider_switch([]) is None
    assert probe.consider_switch(_lines(("a.example", None), ("b.example", None))) is None


def test_an_edge_this_room_is_not_served_from_is_ignored():
    """The comparison can outlive a room change; never point at a stale host."""
    probe = _probe(["a.example"])
    assert probe.consider_switch(_lines(("elsewhere.example", 5.0))) is None
    assert probe.current_host == "a.example"


# ---------------------------------------------------------------- cooldown
def test_two_similar_edges_cannot_trade_the_stream_back_and_forth():
    probe = _probe(["a.example", "b.example"])
    now = time.monotonic()

    assert probe.consider_switch(_lines(("a.example", 200.0), ("b.example", 40.0)), now) is not None
    # b is now in use; a suddenly looks better, but it is far too soon.
    assert probe.consider_switch(_lines(("b.example", 200.0), ("a.example", 40.0)),
                                 now + 5) is None
    assert probe.current_host == "b.example"

    # Once the cooldown is over, a genuine change is allowed again.
    later = probe.consider_switch(_lines(("b.example", 200.0), ("a.example", 40.0)),
                                  now + SWITCH_COOLDOWN_S + 1)
    assert later is not None and later.to_host == "a.example"


# ------------------------------------------------------------------ wiring
def test_the_chosen_endpoint_follows_the_preferred_edge():
    probe = _probe(["slow.example", "fast.example"])
    probe.consider_switch(_lines(("slow.example", 200.0), ("fast.example", 30.0)))

    endpoint = probe.choose_endpoint(probe._endpoints)
    assert endpoint.host == "fast.example"


def test_format_still_outranks_speed():
    """fmp4 carries the server clock; trading it away would cost accuracy."""
    probe = StreamProbe(client=None, auto_cdn=True)
    probe._endpoints = [_endpoint("slow.example", "fmp4"), _endpoint("fast.example", "ts")]
    probe.consider_switch(_lines(("slow.example", 200.0), ("fast.example", 20.0)))

    # The fast edge only offers ts here, so the measurable one is kept.
    assert probe.choose_endpoint(probe._endpoints).fmt == "fmp4"


def test_the_fastest_edge_wins_among_equally_good_formats():
    probe = StreamProbe(client=None, auto_cdn=True)
    probe._endpoints = [
        _endpoint("slow.example", "fmp4"),
        _endpoint("fast.example", "fmp4"),
        _endpoint("fast.example", "ts"),
    ]
    probe.consider_switch(_lines(("slow.example", 200.0), ("fast.example", 20.0)))

    endpoint = probe.choose_endpoint(probe._endpoints)
    assert (endpoint.host, endpoint.fmt) == ("fast.example", "fmp4")


def test_turning_it_off_leaves_the_first_edge_alone():
    probe = _probe(["slow.example", "fast.example"], auto_cdn=False)
    assert probe.consider_switch(_lines(("slow.example", 200.0), ("fast.example", 20.0))) is None
    assert probe.choose_endpoint(probe._endpoints).host == "slow.example"


def test_a_new_room_forgets_the_old_edge_but_keeps_the_record():
    probe = _probe(["slow.example", "fast.example"])
    probe.consider_switch(_lines(("slow.example", 200.0), ("fast.example", 30.0)))
    assert probe.preferred_host == "fast.example"

    probe.set_room("999")
    assert probe.preferred_host == ""
    assert len(probe.switches) == 1        # the history is still worth reporting


def test_the_switch_record_stays_bounded():
    probe = _probe(["a.example", "b.example"])
    for index in range(40):
        # Alternate, ignoring the cooldown by moving the clock along.
        pair = (("a.example", 300.0), ("b.example", 20.0)) if index % 2 == 0 else \
               (("b.example", 300.0), ("a.example", 20.0))
        probe.consider_switch(_lines(*pair), time.monotonic() + index * SWITCH_COOLDOWN_S * 2)

    assert len(probe.switches) <= 20
