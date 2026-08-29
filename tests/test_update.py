"""Update checking: one request, and never a false alarm."""

import json
import time
import urllib.error

import pytest

from lagscope import update
from lagscope.update import UpdateInfo, check, due, fetch_latest, is_newer, parse_version


@pytest.mark.parametrize(
    "text,expected",
    [
        ("v3.5", (3, 5)),
        ("3.0.0", (3, 0, 0)),
        ("LagScope 1.2.1", (1, 2, 1)),
        ("", ()),
        ("nightly", ()),
    ],
)
def test_version_strings_of_every_shape(text, expected):
    assert parse_version(text) == expected


def test_trailing_zeros_are_not_a_new_release():
    # The tags are written both ways; 3.5 and 3.5.0 are the same thing.
    assert not is_newer("3.5.0", "3.5")
    assert not is_newer("3.5", "3.5.0")


@pytest.mark.parametrize(
    "candidate,current,newer",
    [
        ("3.6", "3.5", True),
        ("v4.0", "3.5", True),
        ("3.5.1", "3.5", True),
        ("3.4", "3.5", False),
        ("3.5", "3.5", False),
        ("1.0", "3.5", False),
    ],
)
def test_is_newer(candidate, current, newer):
    assert is_newer(candidate, current) is newer


def test_an_unreadable_version_is_never_an_upgrade():
    # A surprise from the API must not turn into an update prompt.
    assert not is_newer("", "3.5")
    assert not is_newer("nightly-build", "3.5")


def test_checking_is_due_once_a_day():
    now = time.time()
    assert due(0.0) is True                       # never checked
    assert due(now - 10) is False
    assert due(now - 25 * 3600) is True
    assert due(now + 99999) is True               # clock jumped: check anyway


class _Response:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self, *args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_the_tag_and_link_come_back_from_the_api(monkeypatch):
    monkeypatch.setattr(update.urllib.request, "urlopen",
                        lambda *a, **k: _Response({"tag_name": "v9.9",
                                                   "html_url": "https://example/9.9"}))
    found = fetch_latest()
    assert found == UpdateInfo(version="9.9", url="https://example/9.9", notes="")


def test_being_offline_is_not_an_error(monkeypatch):
    def boom(*args, **kwargs):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(update.urllib.request, "urlopen", boom)
    assert fetch_latest() is None
    assert check("3.5", last_checked=0.0) is None


def test_nonsense_from_the_api_is_ignored(monkeypatch):
    for payload in ({"tag_name": ""}, ["not", "a", "dict"], {}):
        def answer(*args, _payload=payload, **kwargs):
            return _Response(_payload)

        monkeypatch.setattr(update.urllib.request, "urlopen", answer)
        assert fetch_latest() is None


def test_a_skipped_version_stays_skipped_until_something_newer(monkeypatch):
    monkeypatch.setattr(update, "fetch_latest",
                        lambda **kwargs: UpdateInfo(version="3.6"))

    assert check("3.5", last_checked=0.0, skip_version="3.6") is None
    assert check("3.5", last_checked=0.0, skip_version="3.5").version == "3.6"
    # ...and a later release gets through the skip.
    monkeypatch.setattr(update, "fetch_latest", lambda **kwargs: UpdateInfo(version="4.0"))
    assert check("3.5", last_checked=0.0, skip_version="3.6").version == "4.0"


def test_nothing_is_requested_when_the_check_is_not_due(monkeypatch):
    calls = []
    monkeypatch.setattr(update, "fetch_latest",
                        lambda **kwargs: calls.append(1) or UpdateInfo(version="9.9"))

    assert check("3.5", last_checked=time.time()) is None
    assert calls == []


def test_the_same_version_is_not_reported_as_an_update(monkeypatch):
    monkeypatch.setattr(update, "fetch_latest", lambda **kwargs: UpdateInfo(version="3.5"))
    assert check("3.5", last_checked=0.0) is None
