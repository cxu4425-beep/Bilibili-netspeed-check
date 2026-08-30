"""The DNS/handshake split, and the answer to "why doesn't this match ping".

The split is the point: the app used to time ``create_connection(hostname)``,
which quietly billed the name lookup to the server's latency. These tests pin
the two apart against a local listener, where the handshake is effectively
free and any DNS cost would stand out.
"""

import socket
import threading

import pytest

from lagscope import pingcompare
from lagscope.i18n import set_language, tr
from lagscope.pingcompare import PingComparison, compare, format_report
from lagscope.probes.network import connect_timing, tcp_rtt_ms


@pytest.fixture
def listener():
    """A socket that accepts and immediately drops, for handshake timing."""
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except OSError:
                return

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield server.getsockname()[1]
    stop.set()
    server.close()


# ------------------------------------------------------------- the split
def test_an_ip_literal_is_not_charged_for_a_name_lookup(listener):
    """Nothing was resolved, so no DNS figure may be invented."""
    timing = connect_timing("127.0.0.1", listener)
    assert timing.ok
    assert timing.dns_ms is None
    assert timing.address == "127.0.0.1"


def test_a_hostname_reports_the_lookup_separately(listener):
    timing = connect_timing("localhost", listener)
    assert timing.ok
    assert timing.dns_ms is not None      # measured, not folded into the RTT
    assert timing.rtt_ms is not None


def test_the_handshake_figure_excludes_the_lookup(listener):
    """Against a loopback listener the handshake is sub-millisecond.

    If the lookup were still counted in, this would carry the resolver's cost.
    """
    timing = connect_timing("localhost", listener)
    assert timing.rtt_ms < 50.0


def test_the_address_actually_connected_to_is_reported(listener):
    timing = connect_timing("localhost", listener)
    assert timing.address in ("127.0.0.1", "::1")


def test_the_old_helper_still_returns_a_bare_number(listener):
    """Every existing caller passes a host and expects a float or None."""
    assert isinstance(tcp_rtt_ms("127.0.0.1", listener), float)
    assert tcp_rtt_ms("127.0.0.1", 1) is None
    assert tcp_rtt_ms("") is None


def test_a_name_that_does_not_resolve_is_reported_not_raised():
    timing = connect_timing("no-such-host.invalid", 443, timeout_s=2.0)
    assert not timing.ok and timing.error
    assert timing.rtt_ms is None


def test_a_refused_port_is_reported_not_raised():
    timing = connect_timing("127.0.0.1", 1, timeout_s=2.0)
    assert not timing.ok and timing.error


# -------------------------------------------------------- the comparison
def test_it_measures_the_same_address_with_both_tools(listener):
    result = compare("localhost", listener, rounds=2, timeout_s=2.0)
    assert result.address in ("127.0.0.1", "::1")
    assert len(result.tcp_samples) >= 1


def test_a_host_that_ignores_icmp_still_produces_a_verdict(listener, monkeypatch):
    monkeypatch.setattr(pingcompare, "icmp_ping_ms", lambda *a, **k: None)
    result = compare("127.0.0.1", listener, rounds=2, timeout_s=2.0)
    assert result.icmp_samples == []
    assert result.verdict_key == "pingcmp.verdict.no_icmp"


def test_an_unreachable_host_says_so_rather_than_comparing_nothing():
    result = compare("127.0.0.1", 1, rounds=1, timeout_s=1.0)
    assert result.error
    assert result.verdict_key == "pingcmp.verdict.no_tcp"


def test_no_host_is_not_an_error_worth_raising():
    assert compare("").error == "no-host"


@pytest.mark.parametrize(
    "tcp,icmp,expected",
    [
        ([20.0], [19.0], "pingcmp.verdict.agree"),      # within noise
        ([30.0], [22.0], "pingcmp.verdict.small"),      # a normal offset
        ([80.0], [20.0], "pingcmp.verdict.wide"),       # different treatment
        ([20.0], [], "pingcmp.verdict.no_icmp"),
        ([], [20.0], "pingcmp.verdict.no_tcp"),
    ],
)
def test_the_verdict_follows_the_numbers(tcp, icmp, expected):
    result = PingComparison(host="h", address="1.2.3.4",
                            tcp_samples=list(tcp), icmp_samples=list(icmp))
    assert result.verdict_key == expected


def test_the_gap_is_tcp_minus_icmp():
    result = PingComparison(tcp_samples=[50.0, 60.0], icmp_samples=[20.0, 30.0])
    assert result.gap_ms == pytest.approx(30.0)      # best against best


def test_the_gap_is_none_when_only_one_side_answered():
    assert PingComparison(tcp_samples=[10.0]).gap_ms is None


# ------------------------------------------------------------- the report
def test_the_report_names_the_address_so_it_can_be_pinged_by_hand():
    result = PingComparison(host="cn-hbyc-ct-01.bilivideo.com", address="1.2.3.4",
                            port=443, dns_ms=12.0,
                            tcp_samples=[40.0], icmp_samples=[38.0])
    set_language("en")
    text = format_report(result)
    assert "1.2.3.4:443" in text
    assert "Yichang" in text                 # the decoder is wired in
    assert tr("pingcmp.verdict.agree") in text
    assert "cdn.op." not in text             # keys must never reach the reader


def test_the_report_warns_when_the_server_is_a_peer_node():
    result = PingComparison(host="xy1x2x3x4xy.mcdn.bilivideo.cn", address="1.2.3.4",
                            tcp_samples=[40.0], icmp_samples=[38.0])
    set_language("en")
    assert tr("cdn.peer.warn") in format_report(result)


def test_the_report_says_so_when_nothing_could_be_measured():
    text = format_report(PingComparison(host="h", error="unreachable"))
    assert "unreachable" in text


@pytest.mark.parametrize("language", ["zh_CN", "zh_TW", "en", "ja", "ko"])
def test_the_report_is_written_in_every_language(language):
    set_language(language)
    result = PingComparison(host="cn-hbyc-ct-01.bilivideo.com", address="1.2.3.4",
                            dns_ms=9.0, tcp_samples=[40.0], icmp_samples=[10.0])
    text = format_report(result)
    assert "pingcmp." not in text            # no untranslated key leaked
    assert "+30.0 ms" in text
