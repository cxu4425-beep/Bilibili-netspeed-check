"""How far away the server can be, from the round trip alone.

Hostname decoding answers "where is this" only when the name says so, and the
two commonest cases - a node rented from a public cloud, and a PCDN peer - say
nothing at all. Physics covers every server without exception, so this is the
half that always works. It is also entirely checkable here, which the hostname
tables are not: no adapter, no network, no fixtures, just arithmetic that is
either right or wrong.
"""

import pytest

from lagscope.i18n import set_language
from lagscope.probes.cdninfo import locate_line
from lagscope.probes.distance import (
    KM_PER_MS, USEFUL_CEILING_KM, contradicts, informative, max_distance_km,
    min_rtt_ms,
)


def test_the_constant_matches_light_in_fibre():
    """c / 1.468 / 2, in km per ms. Getting this wrong would silently skew
    every distance the app ever reports."""
    assert KM_PER_MS == pytest.approx(102.1, abs=0.5)


def test_a_round_trip_buys_about_a_hundred_kilometres_per_millisecond():
    assert max_distance_km(1.0) == pytest.approx(102.1, abs=0.5)
    assert max_distance_km(10.0) == pytest.approx(1021.0, abs=5.0)


def test_the_bound_scales_linearly():
    assert max_distance_km(20.0) == pytest.approx(2 * max_distance_km(10.0))


@pytest.mark.parametrize("rtt", [None, 0, -5])
def test_a_missing_or_impossible_round_trip_yields_nothing(rtt):
    assert max_distance_km(rtt) is None


def test_a_narrow_ceiling_is_worth_reading():
    # 4 ms puts the server inside ~400 km. That is a real statement.
    assert informative(max_distance_km(4.0))


def test_a_ceiling_wider_than_the_planet_says_nothing():
    """Half the world is within 20 000 km, so quoting it is not a location."""
    assert not informative(max_distance_km(300.0))
    assert not informative(None)
    assert informative(USEFUL_CEILING_KM)
    assert not informative(USEFUL_CEILING_KM + 1)


def test_the_physics_reads_backwards_too():
    """Taiwan to Guangzhou is roughly 800 km, so nothing there can answer in
    under about 8 ms however good the line is."""
    assert min_rtt_ms(800.0) == pytest.approx(7.8, abs=0.3)
    assert min_rtt_ms(None) is None
    assert min_rtt_ms(0) is None


def test_a_reply_too_fast_for_the_claimed_distance_is_a_contradiction():
    # A hostname claiming Yichang (~1300 km) that answers in 3 ms is not
    # describing the machine that answered.
    assert contradicts(3.0, 1300.0)


def test_a_plausible_reply_is_not_called_a_contradiction():
    assert not contradicts(38.0, 1300.0)
    assert not contradicts(None, 1300.0)
    assert not contradicts(38.0, None)


def test_the_tolerance_protects_against_jitter_not_against_physics():
    """A borderline case must not be called a lie on the strength of a
    millisecond - a false accusation is worse than staying quiet."""
    needed = min_rtt_ms(1000.0)
    assert not contradicts(needed * 0.95, 1000.0)      # within slack: quiet
    assert contradicts(needed * 0.5, 1000.0)           # nowhere near: flagged


# ------------------------------------------------------- the line people read
@pytest.fixture(autouse=True)
def _language():
    set_language("en")


CLOUD = "upos-sz-mirrorhw.bilivideo.com"
NAMED = "cn-hbyc-ct-01.bilivideo.com"


def test_a_named_host_keeps_its_name_and_gains_a_ceiling():
    line = locate_line(NAMED, 38.0, True)
    assert "China Telecom" in line
    assert "3,880 km" in line


def test_a_cloud_node_gets_a_location_it_could_not_state_itself():
    """The whole point: the hostname says "Huawei Cloud" and nothing about
    where, which is exactly the case the physics has to cover."""
    line = locate_line(CLOUD, 4.0, True)
    assert "408 km" in line


def test_no_ceiling_when_the_round_trip_was_not_to_this_server():
    """The monitor falls back to timing the API host when the edge will not
    answer. That is a different machine somewhere else, so a distance from it
    would be about the wrong thing entirely."""
    line = locate_line(CLOUD, 38.0, False)
    assert "km" not in line


def test_no_ceiling_when_it_would_be_meaningless():
    assert "km" not in locate_line(CLOUD, 260.0, True)


def test_an_unreadable_host_still_produces_the_ceiling_alone():
    line = locate_line("something.unknown.example", 4.0, True)
    assert "408 km" in line
    # and does not repeat the bare hostname next to it
    assert line.count("something.unknown.example") == 0
