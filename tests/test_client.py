"""Reading what the official desktop client is playing, with no user action."""

import sqlite3
import time

import pytest

from lagscope.detect import client as client_source


def _chromium_db(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE urls (id INTEGER, url TEXT, title TEXT, last_visit_time INTEGER)"
    )
    for index, (url, title, ago_s) in enumerate(rows):
        stamp = int((time.time() - ago_s + 11_644_473_600) * 1_000_000)
        connection.execute("INSERT INTO urls VALUES (?,?,?,?)", (index, url, title, stamp))
    connection.commit()
    connection.close()
    return path


# ------------------------------------------------------------------ discovery
def test_client_folders_are_found_next_to_the_config(tmp_path, monkeypatch):
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "bilibili").mkdir()
    (tmp_path / "some-other-app").mkdir()

    roots = client_source.client_roots()

    assert [path.name for path in roots] == ["bilibili"]


def test_one_directory_under_two_names_is_found_once(tmp_path, monkeypatch):
    """Windows and macOS treat "bilibili" and "BiliBili" as the same folder.

    The candidate list spells it several ways on purpose, so on those systems
    the same directory used to come back twice and every scan read the same
    database over again. A symlink reproduces that here on any platform.
    """
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    real = tmp_path / "bilibili"
    real.mkdir()
    (tmp_path / "BiliBili").symlink_to(real, target_is_directory=True)

    roots = client_source.client_roots()

    assert len(roots) == 1


def test_extra_folders_from_the_config_are_used(tmp_path, monkeypatch):
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    custom = tmp_path / "D_drive" / "bili"
    custom.mkdir(parents=True)

    roots = client_source.client_roots([str(custom)])

    assert custom in roots


def test_history_databases_are_found_but_cache_trees_are_skipped(tmp_path):
    root = tmp_path / "bilibili"
    _chromium_db(root / "User Data" / "Default" / "History", [])
    (root / "Cache").mkdir(parents=True)
    (root / "Cache" / "History").write_bytes(b"junk")

    found = client_source.find_history_databases([root])

    assert len(found) == 1
    assert found[0].parent.name == "Default"


def test_deeply_buried_files_are_not_walked_forever(tmp_path):
    root = tmp_path / "bilibili"
    deep = root.joinpath(*[f"level{index}" for index in range(8)])
    deep.mkdir(parents=True)
    (deep / "History").write_bytes(b"junk")

    assert client_source.find_history_databases([root]) == []


# ----------------------------------------------------------------------- logs
def test_room_and_video_ids_are_read_out_of_a_client_log(tmp_path):
    log = tmp_path / "client.log"
    log.write_text(
        "2026-08-27 11:20:01 INFO opening https://www.bilibili.com/video/BV1GJ411x7h7\n"
        '2026-08-27 11:20:02 INFO {"roomid":27182818,"quality":10000}\n'
        "2026-08-27 11:20:05 INFO heartbeat room_id=31415926\n",
        encoding="utf-8",
    )

    entries = client_source.scan_log_file(log)
    urls = [entry.url for entry in entries]

    assert "https://live.bilibili.com/27182818" in urls
    assert "https://live.bilibili.com/31415926" in urls
    assert "https://www.bilibili.com/video/BV1GJ411x7h7" in urls
    assert all(entry.browser == "client-log" for entry in entries)


def test_placeholder_room_ids_are_ignored(tmp_path):
    log = tmp_path / "client.log"
    log.write_text('{"roomid":0}\nroom_id=0\n', encoding="utf-8")
    assert client_source.scan_log_file(log) == []


def test_only_the_tail_of_a_big_log_is_read(tmp_path):
    log = tmp_path / "client.log"
    padding = "x" * (client_source.LOG_TAIL_BYTES + 50_000)
    log.write_text(f"room_id=11111111\n{padding}\nroom_id=22222222\n", encoding="utf-8")

    urls = [entry.url for entry in client_source.scan_log_file(log)]

    assert "https://live.bilibili.com/22222222" in urls
    assert "https://live.bilibili.com/11111111" not in urls   # too far back


def test_recent_logs_are_preferred_and_old_ones_dropped(tmp_path):
    root = tmp_path / "bilibili"
    root.mkdir()
    fresh = root / "fresh.log"
    stale = root / "stale.log"
    fresh.write_text("room_id=1", encoding="utf-8")
    stale.write_text("room_id=2", encoding="utf-8")
    old = time.time() - 86_400
    import os

    os.utime(stale, (old, old))

    files = client_source.find_log_files([root], max_age_s=3600)

    assert files == [fresh]


def test_an_unreadable_log_is_skipped(tmp_path):
    assert client_source.scan_log_file(tmp_path / "missing.log") == []


# -------------------------------------------------------------------- scanner
def test_scanner_reads_the_client_history_first(tmp_path, monkeypatch):
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    root = tmp_path / "bilibili"
    _chromium_db(root / "User Data" / "Default" / "History", [
        ("https://live.bilibili.com/31415926", "某某的直播间", 10),
        ("https://www.bilibili.com/video/BV1GJ411x7h7", "旧影片", 600),
    ])
    (root / "logs").mkdir()
    (root / "logs" / "client.log").write_text("room_id=99999999", encoding="utf-8")

    entries = client_source.ClientScanner().scan()

    assert entries[0].url == "https://live.bilibili.com/31415926"
    assert all("99999999" not in entry.url for entry in entries)   # logs not needed


def test_scanner_falls_back_to_logs_without_a_history_database(tmp_path, monkeypatch):
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    root = tmp_path / "bilibili" / "logs"
    root.mkdir(parents=True)
    (root / "client.log").write_text('{"roomid":27182818}', encoding="utf-8")

    entries = client_source.ClientScanner().scan()

    assert entries and entries[0].url.endswith("/27182818")


def test_scanner_without_any_client_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nothing-here"))
    scanner = client_source.ClientScanner()

    assert scanner.scan() == []
    assert scanner.roots == []


def test_entries_outside_the_window_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _chromium_db(tmp_path / "bilibili" / "User Data" / "Default" / "History",
                 [("https://live.bilibili.com/1", "旧的", 9_000)])

    assert client_source.ClientScanner().scan(window_s=600) == []


def test_discovery_is_cached_until_it_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(client_source.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "bilibili").mkdir()
    scanner = client_source.ClientScanner()
    scanner.discover()

    calls = []
    monkeypatch.setattr(client_source, "client_roots",
                        lambda extra=(): calls.append(1) or [])

    scanner.discover()
    assert calls == []                    # still cached
    scanner.discover(force=True)
    assert len(calls) == 1
