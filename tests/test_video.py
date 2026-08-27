import pytest

from bili_latency.models import KIND_VIDEO
from bili_latency.probes.stream import StreamError
from bili_latency.probes.video import (
    VideoInfo, VideoProbe, VideoStream, choose_video_stream, parse_playurl_video,
    parse_video_id, parse_video_page, parse_video_target, parse_view,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("BV1GJ411x7h7", "BV1GJ411x7h7"),
        ("  BV1GJ411x7h7 ", "BV1GJ411x7h7"),
        ("https://www.bilibili.com/video/BV1GJ411x7h7?p=3&t=10", "BV1GJ411x7h7"),
        ("https://m.bilibili.com/video/BV1GJ411x7h7", "BV1GJ411x7h7"),
        ("av170001", "av170001"),
        ("https://www.bilibili.com/video/av170001/", "av170001"),
        ("170001", "av170001"),
        ("https://live.bilibili.com/123", ""),
        ("https://www.bilibili.com/", ""),
        ("nonsense", ""),
        ("", ""),
    ],
)
def test_parse_video_id(text, expected):
    assert parse_video_id(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://www.bilibili.com/video/BV1GJ411x7h7?p=4", 4),
        ("https://www.bilibili.com/video/BV1GJ411x7h7", 1),
        ("https://www.bilibili.com/video/BV1GJ411x7h7?p=0", 1),
        ("https://www.bilibili.com/video/BV1GJ411x7h7?p=abc", 1),
        ("BV1GJ411x7h7", 1),
    ],
)
def test_parse_video_page(text, expected):
    assert parse_video_page(text) == expected


def test_parse_video_target_returns_both():
    assert parse_video_target("https://www.bilibili.com/video/BV1GJ411x7h7?p=2") == ("BV1GJ411x7h7", 2)


def test_parse_view_picks_the_requested_part():
    payload = {
        "code": 0,
        "data": {
            "bvid": "BV1x", "title": "整部影片", "cid": 1,
            "pages": [
                {"page": 1, "cid": 11, "part": "第一集", "duration": 50},
                {"page": 2, "cid": 22, "part": "第二集", "duration": 60},
            ],
        },
    }
    info = parse_view(payload, "BV1x", page=2)
    assert (info.cid, info.page, info.part_title, info.pages) == (22, 2, "第二集", 2)

    # A part that does not exist falls back to the first one.
    assert parse_view(payload, "BV1x", page=99).cid == 11


def test_parse_view_rejects_an_error_response():
    with pytest.raises(StreamError):
        parse_view({"code": -404, "message": "啥都木有"}, "BV1x")


def test_parse_playurl_reads_dash_and_durl():
    dash = parse_playurl_video({
        "code": 0,
        "data": {"dash": {"video": [
            {"baseUrl": "https://a/1.m4s", "bandwidth": 1_200_000, "id": 64, "codecs": "avc1"},
            {"base_url": "https://b/2.m4s", "bandwidth": 3_000_000, "id": 80,
             "backupUrl": ["https://c/2.m4s"]},
        ]}},
    })
    assert [s.quality for s in dash] == [64, 80]
    assert dash[1].backups == ("https://c/2.m4s",)
    assert choose_video_stream(dash).url == "https://b/2.m4s"

    durl = parse_playurl_video({
        "code": 0,
        "data": {"quality": 32, "durl": [{"url": "https://d/v.mp4", "size": 10_000_000,
                                          "length": 80_000}]},
    })
    assert durl[0].is_dash is False
    assert durl[0].required_mbps == pytest.approx(1.0)


def test_parse_playurl_without_anything_playable():
    with pytest.raises(StreamError):
        parse_playurl_video({"code": 0, "data": {}})
    with pytest.raises(StreamError):
        parse_playurl_video({"code": -10403, "message": "地区限制"})


class FakeResponse:
    status_code = 206

    def __init__(self, chunks):
        self._chunks = chunks

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=8192):
        return iter(self._chunks)

    def close(self):
        pass


class FakeSession:
    def __init__(self, chunks):
        self.chunks = chunks
        self.headers_seen = None

    def get(self, url, headers=None, timeout=None, stream=False):
        self.headers_seen = headers
        return FakeResponse(self.chunks)


class FakeClient:
    def __init__(self, chunks=None, payloads=None):
        self.timeout_s = 4.0
        self.session = FakeSession([b"x" * 65536] * 8 if chunks is None else chunks)
        self.payloads = payloads or []

    def get_json(self, url, params=None, headers=None):
        return self.payloads.pop(0)


def test_measure_stream_reports_throughput_and_startup():
    client = FakeClient(chunks=[b"x" * 65536] * 8)   # 512 KiB
    probe = VideoProbe(client, probe_bytes=512 * 1024)
    stream = VideoStream(url="https://cdn.example.com/v.m4s", bandwidth_bps=3_000_000, quality=80)

    result = probe.measure_stream(stream)

    assert result.kind == KIND_VIDEO and result.method == "video-startup"
    assert result.estimated is True
    assert result.throughput_mbps > 0
    assert result.required_mbps == pytest.approx(3.0)
    assert result.headroom == pytest.approx(result.throughput_mbps / 3.0)
    # start-up = TTFB + one second of video at the measured speed
    assert result.stream_ms == pytest.approx(result.detail["ttfb_ms"] + result.buffer_ms)
    assert client.session.headers_seen["Range"] == "bytes=0-524287"
    assert "bilibili.com" in client.session.headers_seen["Referer"]


def test_measure_stream_without_an_advertised_bitrate():
    probe = VideoProbe(FakeClient(chunks=[b"x" * 65536]), probe_bytes=64 * 1024)
    result = probe.measure_stream(VideoStream(url="https://cdn/v.mp4", bandwidth_bps=0))

    assert result.required_mbps is None
    assert result.headroom is None
    assert result.detail["bitrate_unknown"] is True


def test_measure_stream_rejects_an_empty_body():
    probe = VideoProbe(FakeClient(chunks=[]))
    with pytest.raises(StreamError):
        probe.measure_stream(VideoStream(url="https://cdn/v.m4s", bandwidth_bps=1000))


def test_measure_without_a_video_id_is_a_no_op():
    assert VideoProbe(FakeClient()).measure("").error == "no-video"


def test_measure_turns_api_failures_into_an_error_sample():
    client = FakeClient(payloads=[{"code": -404, "message": "啥都木有"}])
    result = VideoProbe(client).measure("BV1x")
    assert result.stream_ms is None and "啥都木有" in result.error


def test_target_change_invalidates_the_cached_stream():
    probe = VideoProbe(FakeClient())
    probe._info = VideoInfo(video_id="BV1x", cid=1)
    probe._stream = VideoStream(url="https://cdn/v.m4s")
    probe._fetched_at = 12345.0

    probe.set_target("BV2x", 1)

    assert probe._info is None and probe._stream is None and probe._fetched_at == 0.0
