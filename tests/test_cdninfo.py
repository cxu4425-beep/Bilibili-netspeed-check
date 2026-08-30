"""Reading a CDN hostname - and, more importantly, refusing to over-read one.

The value of this decoder is that someone acts on what it says. So the tests
that matter most are not the ones proving it decodes ``cn-hbyc-ct-01``; they
are the ones proving it does not invent a city for a code it does not know.
"""

import pytest

from lagscope.i18n import set_language, tr
from lagscope.probes.cdninfo import (
    CLOUD, PEER, SELF_BUILT, UNKNOWN, describe, summary,
)


# ------------------------------------------------------------- who runs it
@pytest.mark.parametrize(
    "host,operator,kind",
    [
        ("cn-gotcha09.bilivideo.com", "cdn.op.bilibili", SELF_BUILT),
        ("cn-gotcha204.bilivideo.com", "cdn.op.bilibili", SELF_BUILT),
        ("upos-sz-mirrorali.bilivideo.com", "cdn.op.aliyun", CLOUD),
        ("upos-sz-mirrorcos.bilivideo.com", "cdn.op.tencent", CLOUD),
        ("upos-sz-mirrorhw.bilivideo.com", "cdn.op.huawei", CLOUD),
        ("upos-sz-mirrorbos.bilivideo.com", "cdn.op.baidu", CLOUD),
        ("upos-sz-mirrorks3.bilivideo.com", "cdn.op.kingsoft", CLOUD),
        ("cn-hbyc-ct-01.bilivideo.com", "", UNKNOWN),
    ],
)
def test_who_runs_the_node_is_read_from_the_name(host, operator, kind):
    info = describe(host)
    assert info.operator_key == operator
    assert info.kind == kind


def test_a_longer_marker_wins_over_a_prefix_of_itself():
    """``mirrorhwo1`` must not be read as ``mirrorhw`` if they ever differ."""
    assert describe("upos-sz-mirrorhwo1.bilivideo.com").operator_key == "cdn.op.huawei"
    assert describe("upos-sz-mirrorks3ovs.bilivideo.com").operator_key == "cdn.op.kingsoft"


# ------------------------------------------------------------ peer nodes
def test_a_peer_node_is_flagged_and_its_address_read_out():
    info = describe("xy118x123x45x67xy.mcdn.bilivideo.cn")
    assert info.is_peer and info.kind == PEER
    assert info.peer_ip == "118.123.45.67"


def test_a_peer_node_without_the_ip_pattern_is_still_flagged():
    assert describe("something.mcdn.bilivideo.cn").is_peer


def test_an_impossible_address_is_not_reported_as_one():
    """``xy999x…`` is not an IPv4 address, so no address is claimed."""
    info = describe("xy999x999x999x999xy.mcdn.bilivideo.cn")
    assert info.is_peer
    assert info.peer_ip == ""


def test_an_ordinary_edge_is_not_called_a_peer_node():
    assert not describe("cn-hbyc-ct-01.bilivideo.com").is_peer
    assert not describe("upos-sz-mirrorhw.bilivideo.com").is_peer


# --------------------------------------------------------------- location
def test_a_known_city_code_is_decoded():
    info = describe("cn-hbyc-ct-01.bilivideo.com")
    assert info.city_key == "cdn.city.yichang"
    assert info.province_key == "cdn.pr.hubei"
    assert info.region_key == "cdn.region.mainland"
    assert info.carrier_key == "cdn.isp.telecom"


@pytest.mark.parametrize(
    "host,carrier",
    [
        ("cn-jsnj-ct-01.bilivideo.com", "cdn.isp.telecom"),
        ("cn-jsnj-cu-01.bilivideo.com", "cdn.isp.unicom"),
        ("cn-jsnj-cm-01.bilivideo.com", "cdn.isp.mobile"),
    ],
)
def test_the_carrier_marker_is_read(host, carrier):
    assert describe(host).carrier_key == carrier


def test_an_unknown_city_keeps_the_province_and_admits_the_rest():
    """The half it can read is reported; the half it cannot is handed back raw."""
    info = describe("cn-hbqq-cu-02.bilivideo.com")
    assert info.province_key == "cdn.pr.hubei"
    assert info.city_key == ""              # never guessed
    assert info.geo_code == "hbqq"          # but not thrown away either


def test_an_entirely_unknown_code_invents_nothing():
    info = describe("cn-zzz-ct-01.bilivideo.com")
    assert info.city_key == "" and info.province_key == ""
    assert info.geo_code == "zzz"
    assert info.region_key == "cdn.region.mainland"   # this part is still stated


def test_a_hostname_that_says_nothing_claims_nothing():
    info = describe("example.com")
    assert not info.located
    assert info.operator_key == "" and info.carrier_key == ""


def test_an_empty_hostname_is_not_an_error():
    assert describe("").host == ""


# ---------------------------------------------------------------- summary
def test_the_summary_reads_as_a_sentence_fragment():
    set_language("en")
    assert summary("cn-hbyc-ct-01.bilivideo.com") == "Yichang · China Telecom"
    assert summary("upos-sz-mirrorhw.bilivideo.com") == "Huawei Cloud CDN"


def test_an_unrecognised_code_is_shown_rather_than_dropped():
    set_language("en")
    text = summary("cn-hbqq-cu-02.bilivideo.com")
    assert "Hubei" in text and "hbqq" in text


def test_a_hostname_it_cannot_read_comes_back_unchanged():
    assert summary("example.com") == "example.com"


def test_every_key_it_can_produce_actually_translates():
    """A decoder that emits a key with no string would show a raw key to a user."""
    from lagscope.probes.cdninfo import CARRIERS, CITIES, OPERATORS, PROVINCES, REGIONS

    keys = set(PROVINCES.values()) | set(CITIES.values()) | set(REGIONS.values())
    keys |= set(CARRIERS.values()) | {value[0] for value in OPERATORS.values()}
    keys |= {"cdn.op.peer", "cdn.peer.warn"}
    for language in ("zh_CN", "zh_TW", "en", "ja", "ko"):
        set_language(language)
        for key in sorted(keys):
            assert tr(key) != key, f"{key} has no {language} string"
