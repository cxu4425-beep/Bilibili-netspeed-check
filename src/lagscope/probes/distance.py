"""How far away the server can possibly be, from the round trip alone.

Hostname decoding (see cdninfo) answers "where is this server" whenever the
name says so - ``cn-hbyc-ct-01`` is Yichang, on China Telecom. It says nothing
at all for the two cases that matter most in practice: a node rented from a
public cloud (``upos-sz-mirrorhw`` is Huawei Cloud, and that is the whole of
what the name reveals) and a PCDN peer, which is somebody's home connection.

For those, and for every other server, one thing is still knowable: light has
a speed, and a signal cannot have travelled further than that speed allows in
the time the round trip took. That is not an estimate. It is a ceiling, and
the real distance is always under it - real routes bend, and real equipment
takes time to think.

    c                    299 792 km/s
    in single-mode fibre  c / 1.468  =  ~204 000 km/s
    a round trip covers the distance twice

so one millisecond of round-trip time buys about 102 km of separation.

The direction of the claim matters. A *small* ceiling is strong: at 4 ms the
server is within ~400 km and there is no arguing with it. A large ceiling is
nearly worthless - "somewhere within 20 000 km" describes the planet. So
``informative`` exists, and the UI is expected to ask.

Nothing here contacts anything. That is the point: the alternatives are a
bundled GeoIP database, which is stale by the time it ships and which
famously returns the registrant's head office rather than the machine, or an
online lookup, which would mean sending the address of everything you watch
to a third party. This costs a multiplication.
"""

from __future__ import annotations

from typing import Optional

# Speed of light in a vacuum, km/s.
C_KM_S = 299_792.458
# Group index of standard single-mode fibre at 1550 nm. Light in glass is
# slower than light in nothing, and by enough that ignoring it would overstate
# the ceiling by nearly half.
FIBRE_INDEX = 1.468
# Kilometres of separation bought by one millisecond of round trip, halved
# because a round trip covers the distance in both directions.
KM_PER_MS = C_KM_S / FIBRE_INDEX / 1000.0 / 2.0     # ~102.1

# Above this the ceiling stops saying anything: half the planet is within it.
# (Earth's circumference is about 40 075 km, so the furthest any two points
# can be by surface route is roughly 20 000 km.)
USEFUL_CEILING_KM = 10_000.0


def max_distance_km(rtt_ms: Optional[float]) -> Optional[float]:
    """The furthest away a server answering in ``rtt_ms`` could possibly be.

    An upper bound, never an estimate. It assumes a perfectly straight run of
    fibre and equipment that takes no time at all to respond - neither of
    which is ever true - so the real distance is always smaller.
    """
    if rtt_ms is None:
        return None
    value = float(rtt_ms)
    if value <= 0:
        return None
    return value * KM_PER_MS


def informative(km: Optional[float]) -> bool:
    """Whether a ceiling this wide actually narrows anything down."""
    return km is not None and km <= USEFUL_CEILING_KM


def min_rtt_ms(km: Optional[float]) -> Optional[float]:
    """The fastest a server that far away could ever answer.

    The same physics read backwards. Useful for the opposite question: when a
    hostname claims a city, this says whether the round trip is even possible
    for something that far - a reply that arrives sooner than light could
    carry it means the name is not describing the machine that answered.
    """
    if km is None:
        return None
    value = float(km)
    if value <= 0:
        return None
    return value / KM_PER_MS


def contradicts(rtt_ms: Optional[float], claimed_km: Optional[float],
                tolerance: float = 1.15) -> bool:
    """True when the round trip is too fast for the claimed distance.

    The tolerance is slack for the measurement, not for the physics: the
    ceiling itself has none. Without it a borderline case would be called a
    contradiction on the strength of a millisecond of jitter, and a false
    accusation that a hostname is lying is worse than staying quiet.
    """
    needed = min_rtt_ms(claimed_km)
    if needed is None or rtt_ms is None:
        return False
    return float(rtt_ms) * tolerance < needed
