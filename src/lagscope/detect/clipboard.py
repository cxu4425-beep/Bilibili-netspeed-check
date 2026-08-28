"""Picking a Bilibili link out of the clipboard.

This is the detection path for the official Windows/macOS client, where there is
no browser history and no page to run a userscript in: press "share -> copy
link" (分享 -> 复制链接) once and the monitor switches to that room or video.

Only text that actually contains a Bilibili link is ever looked at; everything
else in the clipboard is ignored and never stored or logged.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

LOG = logging.getLogger(__name__)

# Long links, plus the b23.tv short links the share sheet produces.
_URL_RE = re.compile(
    r"https?://(?:"
    r"(?:www\.|m\.|live\.|t\.|space\.)?bilibili\.com/[^\s\"'<>]*"
    r"|b23\.tv/[A-Za-z0-9]+"
    r")",
    re.IGNORECASE,
)
_SHORT_HOSTS = ("b23.tv",)
MAX_CLIPBOARD_CHARS = 4096


def extract_bilibili_url(text: str) -> Optional[str]:
    """First Bilibili URL in a chunk of clipboard text, if any.

    The client copies something like ``【标题】 https://live.bilibili.com/123?…``
    so the link has to be pulled out of surrounding text.
    """
    if not text:
        return None
    match = _URL_RE.search(text[:MAX_CLIPBOARD_CHARS])
    if match is None:
        return None
    # Trailing punctuation from the share text is not part of the URL.
    return match.group(0).rstrip("）)】]，,。.；;、")


def is_short_link(url: str) -> bool:
    return any(host in (url or "").lower() for host in _SHORT_HOSTS)


def expand_short_link(fetch: Callable[[str], Optional[str]], url: str) -> Optional[str]:
    """Resolve a b23.tv link to the page it points at.

    ``fetch`` performs the request and returns the final URL after redirects;
    it is injected so this stays testable and the network stays in one place.
    """
    if not is_short_link(url):
        return url
    try:
        resolved = fetch(url)
    except Exception as exc:  # a dead link must not break detection
        LOG.debug("could not expand %s: %s", url, exc)
        return None
    if not resolved:
        return None
    return resolved
