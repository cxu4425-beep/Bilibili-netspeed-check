"""Turning a Bilibili URL into a watch target.

Every detection source ends up here, so the rules for what counts as a live
room or a video live in exactly one place.
"""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ..models import KIND_LIVE, KIND_VIDEO, WatchTarget

_LIVE_PATH_RE = re.compile(r"^/(?:blanc/|h5/)?(\d{1,12})(?:/|$)")
_VIDEO_PATH_RE = re.compile(r"^/(?:s/)?video/((?:BV[0-9A-Za-z]{10})|(?:av\d{1,12}))(?:/|$)", re.IGNORECASE)


def is_bilibili(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return host == "bilibili.com" or host.endswith(".bilibili.com")


def target_from_url(url: str, title: str = "", source: str = "", ts: Optional[float] = None) -> Optional[WatchTarget]:
    """Return the target a URL points at, or ``None`` if it is not watchable.

    Recognised: ``live.bilibili.com/<room>`` (including /blanc/ and /h5/) and
    ``www.bilibili.com/video/<BV…|av…>`` with an optional ``?p=`` part. Anything
    else - the home page, a space, a bangumi episode - returns ``None`` so the
    detector keeps whatever it had.
    """
    if not is_bilibili(url):
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    query = parse_qs(parsed.query or "")
    detected_at = time.time() if ts is None else ts

    if host.startswith("live."):
        match = _LIVE_PATH_RE.match(path)
        if match:
            return WatchTarget(kind=KIND_LIVE, ident=match.group(1), title=title,
                               source=source, detected_at=detected_at)
        return None

    match = _VIDEO_PATH_RE.match(path)
    if match:
        ident = match.group(1)
        if ident.lower().startswith("av"):
            ident = f"av{ident[2:]}"
        page = 1
        raw_page = (query.get("p") or ["1"])[0]
        try:
            page = max(1, int(raw_page))
        except (TypeError, ValueError):
            page = 1
        return WatchTarget(kind=KIND_VIDEO, ident=ident, page=page, title=title,
                           source=source, detected_at=detected_at)
    return None
