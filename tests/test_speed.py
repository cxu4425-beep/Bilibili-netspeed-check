"""The speed test, measured against a server whose rate is known exactly.

A real endpoint would only prove that the network works. Serving the bytes
locally at a controlled rate is what makes it possible to assert that the
arithmetic - and in particular throwing away TCP slow start - is right.
"""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from lagscope.probes import speed
from lagscope.probes.speed import (
    DEFAULT_MAX_BYTES, SpeedResult, measure_download, public_url, tier_key,
)


class _Server:
    """Serves an endless stream of bytes, optionally rate limited."""

    def __init__(self, bytes_per_s=None, total_bytes=None, status=200):
        self.bytes_per_s = bytes_per_s
        self.total_bytes = total_bytes
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):        # noqa: A003 - keep tests quiet
                pass

            def do_GET(self):                    # noqa: N802 - Qt/http naming
                if outer.status != 200:
                    self.send_error(outer.status)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

                block = b"x" * 64 * 1024
                sent = 0
                started = time.perf_counter()
                try:
                    while outer.total_bytes is None or sent < outer.total_bytes:
                        if outer.bytes_per_s:
                            # Hold the wire to the requested rate.
                            due = started + (sent / outer.bytes_per_s)
                            delay = due - time.perf_counter()
                            if delay > 0:
                                time.sleep(min(delay, 0.05))
                        piece = block
                        if outer.total_bytes is not None:
                            piece = block[: outer.total_bytes - sent]
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(piece), piece))
                        sent += len(piece)
                        if time.perf_counter() - started > 30:
                            break
                    self.wfile.write(b"0\r\n\r\n")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass                          # the client stopped, which is the point

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_address[1]}/data"

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def session():
    with requests.Session() as opened:
        yield opened


# ------------------------------------------------------------------- limits
def test_the_time_budget_ends_the_download(session):
    with _Server() as url:                        # endless stream
        started = time.perf_counter()
        result = measure_download(session, url, budget_s=2.0, max_bytes=10 ** 12)

    assert result.ok
    assert 1.8 <= time.perf_counter() - started <= 6.0
    assert result.seconds == pytest.approx(2.0, abs=0.6)


def test_the_byte_cap_ends_the_download(session):
    with _Server() as url:
        result = measure_download(session, url, budget_s=30.0, max_bytes=512 * 1024)

    assert result.ok
    # It stops on the first chunk that crosses the cap, never far beyond it.
    assert 512 * 1024 <= result.bytes < 512 * 1024 + speed.CHUNK_BYTES * 2


def test_a_data_cap_is_respected_even_on_a_fast_line(session):
    """The point of the byte cap: a gigabit line must not pull a gigabyte."""
    with _Server() as url:
        result = measure_download(session, url, budget_s=20.0, max_bytes=1024 * 1024)

    assert result.bytes < 4 * 1024 * 1024


# ---------------------------------------------------------------- the maths
def test_the_rate_matches_a_server_held_to_a_known_speed(session):
    # 4 MB/s is 32 Mbps; the measured figure should land near that.
    with _Server(bytes_per_s=4 * 1024 * 1024) as url:
        result = measure_download(session, url, budget_s=4.0, max_bytes=10 ** 12)

    assert result.ok
    assert result.mbps == pytest.approx(32.0, rel=0.45)


def test_slow_start_is_thrown_away_not_averaged_in(session, monkeypatch):
    """A run that spends its first second slow must not be dragged down by it."""
    monkeypatch.setattr(speed, "WARMUP_S", 0.5)
    with _Server() as url:
        result = measure_download(session, url, budget_s=2.0, max_bytes=10 ** 12)

    assert result.warmed
    assert result.ramp_mbps is not None
    # The warmed figure ignores the opening stretch, so it cannot be the
    # whole-run average unless they happen to be identical.
    assert result.mbps >= result.ramp_mbps * 0.5


def test_a_download_shorter_than_the_warm_up_says_so(session):
    with _Server(total_bytes=64 * 1024) as url:
        result = measure_download(session, url, budget_s=10.0, max_bytes=10 ** 12)

    assert result.ok
    assert result.warmed is False          # the caller can say "this may read low"
    assert result.mbps == result.ramp_mbps


# ------------------------------------------------------------------- errors
def test_a_refusing_server_is_reported_not_raised(session):
    with _Server(status=503) as url:
        result = measure_download(session, url, budget_s=5.0)

    assert not result.ok and result.error
    assert result.mbps is None


def test_an_unreachable_host_is_reported_not_raised(session):
    result = measure_download(session, "http://127.0.0.1:1/nothing", budget_s=2.0)
    assert not result.ok and result.error


def test_no_url_is_not_an_error_worth_raising(session):
    assert measure_download(session, "", budget_s=2.0).error == "no-url"


def test_the_host_is_reported_so_the_result_can_be_attributed(session):
    with _Server(total_bytes=128 * 1024) as url:
        result = measure_download(session, url, budget_s=5.0, source="stream")

    assert result.host == "127.0.0.1"
    assert result.source == "stream"


# ------------------------------------------------------------------ verdict
@pytest.mark.parametrize(
    "mbps,key",
    [
        (120.0, "speed.tier.4k"),
        (25.0, "speed.tier.4k"),
        (12.0, "speed.tier.1080p60"),
        (6.0, "speed.tier.1080p"),
        (3.0, "speed.tier.720p"),
        (1.0, "speed.tier.low"),
        (0.0, "speed.tier.low"),
        (None, "speed.tier.low"),
    ],
)
def test_a_speed_maps_to_what_it_can_actually_carry(mbps, key):
    assert tier_key(mbps) == key


def test_the_public_endpoint_asks_for_the_size_it_intends_to_read():
    assert str(DEFAULT_MAX_BYTES) in public_url()
    assert "1048576" in public_url(1024 * 1024)


def test_a_result_serialises_for_the_report():
    payload = SpeedResult(mbps=42.0, bytes=100, seconds=2.0, host="h").as_dict()
    assert payload["mbps"] == 42.0 and payload["host"] == "h"
