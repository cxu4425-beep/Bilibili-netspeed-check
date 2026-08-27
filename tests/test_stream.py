import time
from datetime import datetime, timezone

import pytest

from bili_latency.probes.stream import (
    FlvTagParser, StreamEndpoint, StreamError, StreamProbe, parse_m3u8,
    parse_playurl, parse_program_date_time,
)

PLAYLIST_WITH_DATE = """#EXTM3U
#EXT-X-VERSION:7
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:4210
#EXT-X-MAP:URI="h.m4s"
#EXT-X-PROGRAM-DATE-TIME:2026-08-27T09:00:00.000Z
#EXTINF:2.000,
4210.m4s
#EXTINF:2.000,
4211.m4s
#EXTINF:2.000,
4212.m4s
"""

PLAYLIST_WITHOUT_DATE = """#EXTM3U
#EXT-X-TARGETDURATION:4
#EXT-X-MEDIA-SEQUENCE:17
#EXTINF:4.000,
a.ts
#EXTINF:4.000,
b.ts
"""


def test_parse_playlist_with_program_date_time():
    playlist = parse_m3u8(PLAYLIST_WITH_DATE, base_url="https://cdn.example.com/live/index.m3u8")
    assert playlist.target_duration == 2.0
    assert playlist.media_sequence == 4210
    assert len(playlist.segments) == 3
    assert playlist.window_s == 6.0
    assert playlist.segments[0].uri == "https://cdn.example.com/live/4210.m4s"
    # first segment starts at 09:00:00Z, three 2 s segments follow it
    assert playlist.edge_epoch() == pytest.approx(
        parse_program_date_time("2026-08-27T09:00:00Z") + 6.0
    )


def test_parse_playlist_without_program_date_time():
    playlist = parse_m3u8(PLAYLIST_WITHOUT_DATE)
    assert playlist.edge_epoch() is None
    assert playlist.average_segment_s == 4.0
    assert playlist.end_list is False


def test_parse_program_date_time_variants():
    assert parse_program_date_time("2026-08-27T09:00:00Z") == pytest.approx(1787821200.0)
    assert parse_program_date_time("2026-08-27T17:00:00+08:00") == pytest.approx(1787821200.0)
    assert parse_program_date_time("nonsense") is None
    assert parse_program_date_time("") is None


def test_parse_playurl_flattens_every_variant():
    payload = {
        "data": {
            "playurl_info": {
                "playurl": {
                    "stream": [
                        {
                            "protocol_name": "http_hls",
                            "format": [
                                {
                                    "format_name": "fmp4",
                                    "codec": [
                                        {
                                            "codec_name": "avc",
                                            "base_url": "/live/1.m3u8",
                                            "current_qn": 10000,
                                            "url_info": [
                                                {"host": "https://a.example.com", "extra": "?k=1"},
                                                {"host": "https://b.example.com", "extra": "?k=2"},
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "protocol_name": "http_stream",
                            "format": [
                                {
                                    "format_name": "flv",
                                    "codec": [
                                        {
                                            "base_url": "/live/1.flv",
                                            "url_info": [{"host": "https://c.example.com", "extra": ""}],
                                        }
                                    ],
                                }
                            ],
                        },
                    ]
                }
            }
        }
    }
    endpoints = parse_playurl(payload)
    assert [e.url for e in endpoints] == [
        "https://a.example.com/live/1.m3u8?k=1",
        "https://b.example.com/live/1.m3u8?k=2",
        "https://c.example.com/live/1.flv",
    ]
    assert endpoints[0].is_hls and endpoints[0].host == "a.example.com"
    assert not endpoints[2].is_hls


def test_parse_playurl_of_empty_response():
    assert parse_playurl({}) == []
    assert parse_playurl({"data": {"playurl_info": None}}) == []


# ------------------------------------------------------------------------ FLV
def _flv_tag(tag_type: int, timestamp: int, payload: bytes) -> bytes:
    return (
        (0).to_bytes(4, "big")
        + bytes([tag_type])
        + len(payload).to_bytes(3, "big")
        + (timestamp & 0xFFFFFF).to_bytes(3, "big")
        + bytes([(timestamp >> 24) & 0xFF])
        + b"\x00\x00\x00"
        + payload
    )


def _flv_stream() -> bytes:
    return (
        b"FLV\x01\x05" + (9).to_bytes(4, "big")
        + _flv_tag(18, 0, b"onMetaData")
        + _flv_tag(8, 0, b"\xaf\x00audio")
        + _flv_tag(9, 33, b"\x27\x01inter")     # inter frame
        + _flv_tag(9, 66, b"\x17\x01keyframe")  # key frame
    )


def test_flv_parser_finds_the_key_frame():
    tags = list(FlvTagParser().feed(_flv_stream()))
    assert [t.tag_type for t in tags] == [18, 8, 9, 9]
    assert [t.is_keyframe for t in tags] == [False, False, False, True]
    assert tags[-1].timestamp_ms == 66


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 64])
def test_flv_parser_is_chunk_size_independent(chunk_size):
    data = _flv_stream()
    parser = FlvTagParser()
    tags = []
    for index in range(0, len(data), chunk_size):
        tags.extend(parser.feed(data[index:index + chunk_size]))
    assert sum(1 for tag in tags if tag.is_keyframe) == 1


def test_flv_parser_rejects_other_formats():
    with pytest.raises(StreamError):
        list(FlvTagParser().feed(b"NOTFLV\x00\x00\x00\x00\x00\x00"))


# ---------------------------------------------------------------- StreamProbe
class FakeClient:
    """Stands in for HttpClient without touching the network."""

    def __init__(self, text="", json_payload=None, ttfb_ms=12.0):
        self.timeout_s = 4.0
        self.text = text
        self.json_payload = json_payload or {}
        self.ttfb_ms = ttfb_ms
        self.requested = []

    def get_text_timed(self, url):
        self.requested.append(url)
        return self.text, self.ttfb_ms, None

    def get_json(self, url, params=None):
        self.requested.append(url)
        return self.json_payload


def _playlist_now(offset_s: float = 3.0, segment_s: float = 2.0, count: int = 3) -> str:
    """Playlist whose newest segment ends ``offset_s`` seconds ago."""
    start = time.time() - offset_s - segment_s * count
    # Millisecond precision, so the assertions are not fighting truncation.
    stamp = datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    lines = [
        "#EXTM3U",
        "#EXT-X-TARGETDURATION:2",
        "#EXT-X-MEDIA-SEQUENCE:100",
        f"#EXT-X-PROGRAM-DATE-TIME:{stamp}Z",
    ]
    for index in range(count):
        lines += [f"#EXTINF:{segment_s:.3f},", f"{index}.m4s"]
    return "\n".join(lines) + "\n"


def test_measure_hls_uses_the_server_clock_when_available():
    client = FakeClient(text=_playlist_now(offset_s=3.0))
    probe = StreamProbe(client, player_buffer_segments=1.0)
    endpoint = StreamEndpoint(url="https://cdn.example.com/live/1.m3u8", protocol="http_hls", fmt="fmp4")

    result = probe.measure_hls(endpoint)

    assert result.method == "hls-pdt"
    assert result.estimated is False
    assert result.edge_lag_ms == pytest.approx(3000, abs=200)
    assert result.buffer_ms == pytest.approx(2000, abs=1)
    # edge lag + one buffered segment + ttfb
    assert result.stream_ms == pytest.approx(5012, abs=200)


def test_measure_hls_falls_back_to_the_playlist_window():
    client = FakeClient(text=PLAYLIST_WITHOUT_DATE)
    probe = StreamProbe(client, player_buffer_segments=1.0)
    endpoint = StreamEndpoint(url="https://cdn.example.com/live/1.m3u8", protocol="http_hls", fmt="ts")

    result = probe.measure_hls(endpoint)

    assert result.method == "hls-window"
    assert result.estimated is True
    assert result.stream_ms == pytest.approx(4000 * 2 + 12, abs=1)


def test_measure_hls_ignores_an_absurd_client_clock():
    client = FakeClient(text=_playlist_now(offset_s=90_000.0))
    probe = StreamProbe(client)
    endpoint = StreamEndpoint(url="https://cdn.example.com/live/1.m3u8", protocol="http_hls", fmt="fmp4")

    result = probe.measure_hls(endpoint)

    assert result.method == "hls-window"
    assert "rejected_edge_lag_ms" in result.detail


def test_measure_hls_rejects_an_empty_playlist():
    probe = StreamProbe(FakeClient(text="#EXTM3U\n"))
    endpoint = StreamEndpoint(url="https://cdn.example.com/live/1.m3u8", protocol="http_hls", fmt="fmp4")
    with pytest.raises(StreamError):
        probe.measure_hls(endpoint)


def test_measure_reports_an_offline_room_without_probing():
    client = FakeClient(json_payload={"code": 0, "data": {"room_id": 7, "live_status": 0}})
    probe = StreamProbe(client)

    result = probe.measure("7")

    assert result.error == "offline"
    assert result.stream_ms is None
    assert probe.room_info is not None and not probe.room_info.is_live


def test_measure_without_a_room_id_is_a_no_op():
    result = StreamProbe(FakeClient()).measure("")
    assert result.error == "no-room"


def test_measure_reports_api_errors():
    client = FakeClient(json_payload={"code": 1002, "message": "房间不存在"})
    result = StreamProbe(client).measure("999999999")
    assert result.stream_ms is None
    assert "房间不存在" in (result.error or "")


def test_choose_endpoint_prefers_fmp4_then_flv():
    probe = StreamProbe(FakeClient(), prefer_hls=True)
    flv = StreamEndpoint(url="https://c/1.flv", protocol="http_stream", fmt="flv")
    ts = StreamEndpoint(url="https://c/1.m3u8", protocol="http_hls", fmt="ts")
    fmp4 = StreamEndpoint(url="https://c/2.m3u8", protocol="http_hls", fmt="fmp4")

    assert probe.choose_endpoint([flv, ts, fmp4]) is fmp4
    assert probe.choose_endpoint([flv, ts]) is ts
    assert probe.choose_endpoint([]) is None

    flv_first = StreamProbe(FakeClient(), prefer_hls=False)
    assert flv_first.choose_endpoint([ts, flv]) is flv
