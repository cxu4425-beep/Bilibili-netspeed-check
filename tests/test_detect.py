"""Auto-detection: URLs, browser history, window titles, the bridge, and the
priority rules that combine them."""

import json
import sqlite3
import time
import urllib.error
import urllib.request

import pytest

from bili_latency.config import DetectConfig
from bili_latency.detect import history as history_source
from bili_latency.detect import titles as title_source
from bili_latency.detect.bridge import BridgeServer
from bili_latency.detect.manager import AutoDetector
from bili_latency.detect.urls import is_bilibili, target_from_url
from bili_latency.models import KIND_LIVE, KIND_VIDEO


# ----------------------------------------------------------------------- URLs
@pytest.mark.parametrize(
    "url,kind,ident,page",
    [
        ("https://live.bilibili.com/21452505", KIND_LIVE, "21452505", 1),
        ("https://live.bilibili.com/21452505?spm_id_from=x", KIND_LIVE, "21452505", 1),
        ("https://live.bilibili.com/blanc/1234", KIND_LIVE, "1234", 1),
        ("https://live.bilibili.com/h5/9999", KIND_LIVE, "9999", 1),
        ("https://www.bilibili.com/video/BV1GJ411x7h7", KIND_VIDEO, "BV1GJ411x7h7", 1),
        ("https://www.bilibili.com/video/BV1GJ411x7h7?p=3", KIND_VIDEO, "BV1GJ411x7h7", 3),
        ("https://m.bilibili.com/video/av170001", KIND_VIDEO, "av170001", 1),
    ],
)
def test_watchable_urls(url, kind, ident, page):
    target = target_from_url(url, source="test")
    assert target is not None
    assert (target.kind, target.ident, target.page, target.source) == (kind, ident, page, "test")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/",
        "https://live.bilibili.com/",
        "https://space.bilibili.com/123",
        "https://www.bilibili.com/bangumi/play/ep123",   # not supported yet
        "https://evil.example.com/live.bilibili.com/1",
        "not a url",
        "",
    ],
)
def test_urls_that_are_not_watchable(url):
    assert target_from_url(url) is None


def test_is_bilibili_matches_only_real_subdomains():
    assert is_bilibili("https://live.bilibili.com/1")
    assert is_bilibili("https://bilibili.com/")
    assert not is_bilibili("https://bilibili.com.evil.net/")
    assert not is_bilibili("https://youtube.com/")


def test_a_page_number_is_carried_but_never_below_one():
    assert target_from_url("https://www.bilibili.com/video/BV1GJ411x7h7?p=0").page == 1
    assert target_from_url("https://www.bilibili.com/video/BV1GJ411x7h7?p=x").page == 1


# -------------------------------------------------------------------- history
def _chromium_db(path, rows):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE urls (id INTEGER, url TEXT, title TEXT, last_visit_time INTEGER)")
    for index, (url, title, ago_s) in enumerate(rows):
        stamp = int((time.time() - ago_s + 11_644_473_600) * 1_000_000)
        connection.execute("INSERT INTO urls VALUES (?,?,?,?)", (index, url, title, stamp))
    connection.commit()
    connection.close()
    return path


def _firefox_db(path, rows):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE moz_places (id INTEGER, url TEXT, title TEXT, last_visit_date INTEGER)")
    for index, (url, title, ago_s) in enumerate(rows):
        stamp = int((time.time() - ago_s) * 1_000_000)
        connection.execute("INSERT INTO moz_places VALUES (?,?,?,?)", (index, url, title, stamp))
    connection.commit()
    connection.close()
    return path


def test_timestamp_conversions():
    now = time.time()
    assert history_source.chromium_time_to_epoch(int((now + 11_644_473_600) * 1e6)) == pytest.approx(now, abs=1)
    assert history_source.firefox_time_to_epoch(int(now * 1e6)) == pytest.approx(now, abs=1)


def test_reads_only_bilibili_rows_newest_first(tmp_path):
    database = _chromium_db(tmp_path / "History", [
        ("https://example.com/other", "something else", 5),
        ("https://live.bilibili.com/21452505", "某某的直播间", 120),
        ("https://www.bilibili.com/video/BV1GJ411x7h7", "某影片", 10),
    ])
    entries = history_source.read_history(database, "chrome")

    assert [entry.url for entry in entries] == [
        "https://www.bilibili.com/video/BV1GJ411x7h7",
        "https://live.bilibili.com/21452505",
    ]
    assert entries[0].browser == "chrome"


def test_reads_firefox_places(tmp_path):
    database = _firefox_db(tmp_path / "places.sqlite", [
        ("https://live.bilibili.com/777", "直播间", 30),
    ])
    entries = history_source.read_history(database, "firefox", firefox=True)
    assert entries[0].url.endswith("/777")


def test_the_original_file_is_never_opened_for_writing(tmp_path):
    database = _chromium_db(tmp_path / "History", [("https://live.bilibili.com/1", "t", 1)])
    before = database.stat().st_mtime_ns
    history_source.read_history(database, "chrome")
    assert database.stat().st_mtime_ns == before


def test_scan_drops_entries_outside_the_window(tmp_path):
    database = _chromium_db(tmp_path / "History", [
        ("https://live.bilibili.com/1", "recent", 30),
        ("https://live.bilibili.com/2", "old", 4000),
    ])
    databases = [("chrome", database, False)]

    fresh = history_source.scan(window_s=300, databases=databases)
    everything = history_source.scan(window_s=7200, databases=databases)

    assert [entry.title for entry in fresh] == ["recent"]
    assert len(everything) == 2


def test_a_broken_database_is_skipped(tmp_path):
    broken = tmp_path / "History"
    broken.write_bytes(b"this is not sqlite")
    assert history_source.scan(databases=[("chrome", broken, False)]) == []
    assert history_source.scan(databases=[("chrome", tmp_path / "missing", False)]) == []


# --------------------------------------------------------------------- titles
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("某某的直播间 - Google Chrome", "某某的直播间"),
        ("影片标题_哔哩哔哩 - Mozilla Firefox", "影片标题_哔哩哔哩"),
        ("页面 and 3 more pages - Brave", "页面"),
        ("plain title", "plain title"),
    ],
)
def test_normalize_title(raw, expected):
    assert title_source.normalize_title(raw) == expected


def test_title_matching_needs_a_real_overlap():
    windows = ["某某的直播间 - 哔哩哔哩直播 - Google Chrome", "Terminal"]
    assert title_source.title_matches("某某的直播间 - 哔哩哔哩直播", windows)
    assert not title_source.title_matches("完全不同的页面标题", windows)
    assert not title_source.title_matches("短", windows)      # too short to be evidence
    assert not title_source.title_matches("某某的直播间", [])


# --------------------------------------------------------------------- bridge
def _post(port, payload, origin="https://live.bilibili.com"):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/report",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read())


@pytest.fixture
def bridge():
    server = BridgeServer(port=0)
    # Port 0 lets the OS choose a free one; read it back for the requests.
    assert server.start()
    server.port = server._server.server_address[1]
    yield server
    server.stop()


def test_bridge_accepts_a_report_from_bilibili(bridge):
    status, body = _post(bridge.port, {"url": "https://live.bilibili.com/21452505", "title": "直播间"})

    assert status == 200 and body["watched"] is True
    target = bridge.latest()
    assert target.kind == KIND_LIVE and target.ident == "21452505" and target.source == "bridge"


def test_bridge_clears_the_target_when_you_navigate_away(bridge):
    _post(bridge.port, {"url": "https://live.bilibili.com/1", "title": "t"})
    _post(bridge.port, {"url": "https://www.bilibili.com/", "title": "home"})
    assert bridge.latest() is None


def test_bridge_refuses_other_origins(bridge):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(bridge.port, {"url": "https://live.bilibili.com/1"}, origin="https://evil.example.com")
    assert excinfo.value.code == 403
    assert bridge.latest() is None


def test_bridge_reports_go_stale(bridge):
    _post(bridge.port, {"url": "https://live.bilibili.com/1", "title": "t"})
    bridge.timeout_s = 0.0
    assert bridge.latest() is None


def test_bridge_rejects_junk(bridge):
    with pytest.raises(urllib.error.HTTPError):
        request = urllib.request.Request(
            f"http://127.0.0.1:{bridge.port}/report", data=b"not json",
            headers={"Content-Type": "application/json", "Origin": "https://live.bilibili.com"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=3)


# -------------------------------------------------------------------- manager
class FakeBridge:
    def __init__(self, target=None):
        self.target = target
        self.running = True
        self.port = 1
        self.timeout_s = 120.0

    def latest(self):
        return self.target

    def start(self):
        return True

    def stop(self):
        self.running = False


def _detector(monkeypatch, entries=(), titles=(), **config_kwargs):
    config = DetectConfig(**config_kwargs)
    monkeypatch.setattr(history_source, "scan", lambda **kwargs: list(entries))
    monkeypatch.setattr(title_source, "window_titles", lambda: list(titles))
    return AutoDetector(config)


def _entry(url, title, ago_s=10):
    return history_source.HistoryEntry(url=url, title=title, visited_at=time.time() - ago_s)


def test_detector_returns_nothing_when_disabled(monkeypatch):
    detector = _detector(monkeypatch, entries=[_entry("https://live.bilibili.com/1", "t")],
                         enabled=False)
    assert detector.poll() is None


def test_detector_picks_the_newest_history_entry(monkeypatch):
    entries = [
        _entry("https://www.bilibili.com/video/BV1GJ411x7h7?p=2", "影片", ago_s=5),
        _entry("https://live.bilibili.com/21452505", "直播间", ago_s=60),
    ]
    detector = _detector(monkeypatch, entries=entries, use_titles=False)

    target = detector.poll()

    assert target.kind == KIND_VIDEO and target.ident == "BV1GJ411x7h7" and target.page == 2
    assert target.source == "history"


def test_the_window_title_wins_over_recency(monkeypatch):
    entries = [
        _entry("https://www.bilibili.com/video/BV1GJ411x7h7", "刚打开的影片", ago_s=5),
        _entry("https://live.bilibili.com/21452505", "我正在看的直播间", ago_s=600),
    ]
    detector = _detector(monkeypatch, entries=entries,
                         titles=["我正在看的直播间 - 哔哩哔哩直播 - Google Chrome"])

    target = detector.poll()

    assert target.ident == "21452505" and target.source == "history+title"


def test_the_bridge_outranks_the_history(monkeypatch):
    entries = [_entry("https://live.bilibili.com/1", "直播间")]
    detector = _detector(monkeypatch, entries=entries)
    detector._bridge = FakeBridge(target_from_url("https://live.bilibili.com/999", source="bridge"))

    target = detector.poll()

    assert target.ident == "999" and target.source == "bridge"


def test_history_scans_are_rate_limited(monkeypatch):
    calls = []

    def counting_scan(**kwargs):
        calls.append(1)
        return [_entry("https://live.bilibili.com/1", "直播间")]

    detector = _detector(monkeypatch, poll_interval_s=300)
    monkeypatch.setattr(history_source, "scan", counting_scan)

    first = detector.poll()
    second = detector.poll()

    assert len(calls) == 1                    # the second poll reused the answer
    assert second is first
    detector.poll(force=True)
    assert len(calls) == 2


def test_a_failing_history_scan_does_not_raise(monkeypatch):
    detector = _detector(monkeypatch)

    def boom(**kwargs):
        raise sqlite3.DatabaseError("locked")

    monkeypatch.setattr(history_source, "scan", boom)
    assert detector.poll(force=True) is None


def test_history_entries_that_are_not_watchable_are_ignored(monkeypatch):
    detector = _detector(monkeypatch, entries=[_entry("https://www.bilibili.com/", "首页")])
    assert detector.poll() is None
