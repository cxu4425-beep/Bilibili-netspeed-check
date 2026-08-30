"""Telling you when a newer version exists - and nothing else.

People who download a .zip once never hear about the next version. That is the
whole problem this solves, so the solution is kept as small as the problem:

* one HTTPS GET to the GitHub releases API, at most once a day;
* the answer is a version string and a link, which is shown in the tray;
* nothing is downloaded, nothing is installed, nothing is executed.

No identifier, no counter, no usage data is sent - GitHub sees an anonymous
request for a public page, exactly as a browser would. It can be turned off in
the settings, and the first-run wizard asks about it rather than assuming.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from . import REPO_URL, __version__

LOG = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/cxu4425-beep/LagScope/releases/latest"
RELEASES_PAGE = f"{REPO_URL}/releases/latest"
CHECK_INTERVAL_S = 24 * 3600
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


@dataclass(frozen=True)
class UpdateInfo:
    version: str                  # as published, e.g. "3.5"
    url: str = RELEASES_PAGE
    notes: str = ""
    # What the release published for download, so the app can offer to install
    # it rather than only linking to it. Empty when the API said nothing.
    assets: tuple = ()

    @property
    def installer(self):
        """The Windows installer asset, when this release has one."""
        from .selfupdate import pick_installer

        return pick_installer(self.assets)


def parse_version(text: str) -> Tuple[int, ...]:
    """``v3.5`` / ``3.5.0`` / ``LagScope 1.2.1`` -> a comparable tuple.

    Unparseable input becomes ``()``, which compares lower than any real
    version, so a surprise from the API can never look like an upgrade.
    """
    match = _VERSION_RE.search(text or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a later version than ``current``.

    Trailing zeros do not count as a difference: 3.5 and 3.5.0 are the same
    release, which matters because the tags are written both ways.
    """
    left, right = parse_version(candidate), parse_version(current)
    if not left:
        return False
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def fetch_latest(timeout_s: float = 6.0, url: str = RELEASES_API) -> Optional[UpdateInfo]:
    """Ask GitHub what the newest release is. ``None`` on any failure.

    Being offline, rate limited or behind a proxy that blocks this is normal
    and must never surface as an error: the app works fine either way.
    """
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"LagScope/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            payload = json.loads(response.read(1024 * 1024).decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        LOG.debug("update check failed: %s", exc)
        return None
    if not isinstance(payload, dict):
        return None
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        return None
    from .selfupdate import parse_assets

    return UpdateInfo(
        version=tag.lstrip("vV"),
        url=str(payload.get("html_url") or RELEASES_PAGE),
        notes=str(payload.get("name") or ""),
        assets=tuple(parse_assets(payload)),
    )


def due(last_checked: float, now: Optional[float] = None,
        interval_s: float = CHECK_INTERVAL_S) -> bool:
    """Once a day is plenty; a clock that jumped backwards also counts."""
    now = time.time() if now is None else now
    if last_checked <= 0:
        return True
    return not (0 <= now - last_checked < interval_s)


def check(current: str = __version__, last_checked: float = 0.0,
          skip_version: str = "", timeout_s: float = 6.0,
          url: str = RELEASES_API) -> Optional[UpdateInfo]:
    """The whole flow: due? ask; newer? report - unless it was skipped."""
    if not due(last_checked):
        return None
    latest = fetch_latest(timeout_s=timeout_s, url=url)
    if latest is None or not is_newer(latest.version, current):
        return None
    if skip_version and not is_newer(latest.version, skip_version):
        return None
    return latest
