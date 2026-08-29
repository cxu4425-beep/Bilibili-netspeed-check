"""Server -> client probe for an ordinary Bilibili video (VOD).

A recorded video has no live edge, so "delay" means something different from a
live room. What actually matters when watching a VOD is how long you wait for
the picture and whether the connection can keep up with the bitrate, so this
probe measures:

* **TTFB** from the CDN that serves the video file (measured),
* **throughput** of a real ranged download (measured),
* **start-up delay**: TTFB plus the time that throughput needs to fetch one
  second of video at the chosen quality (derived from the two measurements),
* **headroom**: measured throughput divided by the bitrate the quality needs -
  below 1.0x playback will stall, above ~2x it is comfortable.

Like the live probe, this only calls the public web endpoints and never logs in.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

from ..models import KIND_VIDEO, StreamMeasurement
from .network import HttpClient, tcp_rtt_ms
from .stream import StreamError

VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"

VIDEO_HEADERS = {
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}

_BVID_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
_AVID_RE = re.compile(r"(?:^|/|av)(\d{1,12})$", re.IGNORECASE)


def parse_video_id(text: str) -> str:
    """Accept a BV id, an av number, or a bilibili video URL."""
    text = (text or "").strip()
    if not text:
        return ""
    match = _BVID_RE.search(text)
    if match:
        return match.group(1)
    lowered = text.lower()
    if "bilibili.com" in lowered:
        path = urlparse(text).path.rstrip("/")
        avid = _AVID_RE.search(path)
        if avid and "video/av" in lowered:
            return f"av{avid.group(1)}"
        return ""
    if lowered.startswith("av") and text[2:].isdigit():
        return f"av{text[2:]}"
    if text.isdigit():
        return f"av{text}"
    return ""


def parse_video_page(text: str) -> int:
    """Part number from a ``?p=`` query, defaulting to 1."""
    try:
        raw = parse_qs(urlparse((text or "").strip()).query).get("p", ["1"])[0]
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def parse_video_target(text: str) -> tuple:
    """``(video_id, page)`` from anything a user might paste."""
    return parse_video_id(text), parse_video_page(text)


@dataclass(frozen=True)
class VideoInfo:
    video_id: str                 # BV id or avNNN as given
    cid: int
    title: str = ""
    part_title: str = ""
    duration_s: int = 0
    page: int = 1
    pages: int = 1


@dataclass(frozen=True)
class VideoStream:
    url: str
    bandwidth_bps: int = 0
    quality: int = 0
    codec: str = ""
    is_dash: bool = True
    backups: tuple = field(default_factory=tuple)

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or ""

    @property
    def required_mbps(self) -> Optional[float]:
        return self.bandwidth_bps / 1_000_000.0 if self.bandwidth_bps else None


def _id_params(video_id: str) -> dict:
    """Bilibili takes either ``bvid`` or a numeric ``aid``."""
    if video_id.lower().startswith("av") and video_id[2:].isdigit():
        return {"aid": int(video_id[2:])}
    return {"bvid": video_id}


def parse_view(payload: dict, video_id: str, page: int = 1) -> VideoInfo:
    if payload.get("code") != 0:
        raise StreamError(str(payload.get("message") or payload.get("msg") or "view failed"))
    data = payload.get("data") or {}
    pages = data.get("pages") or []
    page = max(1, int(page or 1))
    entry = None
    for candidate in pages:
        if int(candidate.get("page") or 0) == page:
            entry = candidate
            break
    if entry is None and pages:
        entry = pages[0]
        page = int(entry.get("page") or 1)
    cid = int((entry or {}).get("cid") or data.get("cid") or 0)
    if not cid:
        raise StreamError("no playable part in response")
    return VideoInfo(
        video_id=str(data.get("bvid") or video_id),
        cid=cid,
        title=str(data.get("title") or ""),
        part_title=str((entry or {}).get("part") or ""),
        duration_s=int((entry or {}).get("duration") or data.get("duration") or 0),
        page=page,
        pages=max(1, len(pages)),
    )


def parse_playurl_video(payload: dict) -> list[VideoStream]:
    """Flatten a player/playurl response into candidate video streams."""
    if payload.get("code") != 0:
        raise StreamError(str(payload.get("message") or payload.get("msg") or "playurl failed"))
    data = payload.get("data") or payload.get("result") or {}
    streams: list[VideoStream] = []

    dash = data.get("dash") or {}
    for entry in dash.get("video") or []:
        url = str(entry.get("baseUrl") or entry.get("base_url") or "")
        if not url:
            continue
        backups = tuple(str(u) for u in (entry.get("backupUrl") or entry.get("backup_url") or []) if u)
        streams.append(
            VideoStream(
                url=url,
                bandwidth_bps=int(entry.get("bandwidth") or 0),
                quality=int(entry.get("id") or 0),
                codec=str(entry.get("codecs") or ""),
                is_dash=True,
                backups=backups,
            )
        )

    if not streams:
        # Older/fallback format: a whole progressive file per segment.
        quality = int(data.get("quality") or 0)
        for entry in data.get("durl") or []:
            url = str(entry.get("url") or "")
            if not url:
                continue
            size = int(entry.get("size") or 0)
            length_ms = int(entry.get("length") or 0)
            bandwidth = int(size * 8 / (length_ms / 1000.0)) if size and length_ms else 0
            backups = tuple(str(u) for u in (entry.get("backup_url") or []) if u)
            streams.append(
                VideoStream(url=url, bandwidth_bps=bandwidth, quality=quality,
                            is_dash=False, backups=backups)
            )
    if not streams:
        raise StreamError("no playable stream in response")
    return streams


def choose_video_stream(streams: list[VideoStream]) -> Optional[VideoStream]:
    """Pick the best quality the API handed out (that is what the player plays)."""
    if not streams:
        return None
    return max(streams, key=lambda s: (s.quality, s.bandwidth_bps))


class VideoProbe:
    def __init__(self, client: HttpClient, *, probe_bytes: int = 512 * 1024,
                 playurl_refresh_s: int = 240) -> None:
        self.client = client
        self.probe_bytes = max(64 * 1024, int(probe_bytes))
        self.playurl_refresh_s = playurl_refresh_s
        self._video_id = ""
        self._page = 1
        self._info: Optional[VideoInfo] = None
        self._stream: Optional[VideoStream] = None
        self._fetched_at = 0.0

    # ------------------------------------------------------------------ state
    def set_target(self, video_id: str, page: int = 1) -> None:
        if (video_id, page) != (self._video_id, self._page):
            self._video_id = video_id
            self._page = max(1, int(page or 1))
            self.invalidate()

    def invalidate(self) -> None:
        self._info = None
        self._stream = None
        self._fetched_at = 0.0

    @property
    def info(self) -> Optional[VideoInfo]:
        return self._info

    def endpoint_rtt_ms(self, timeout_s: float = 4.0) -> Optional[float]:
        if self._stream is None:
            return None
        parsed = urlparse(self._stream.url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return tcp_rtt_ms(self._stream.host, port, timeout_s)

    def bulk_url(self) -> str:
        """The media file already chosen for this video - a real payload."""
        return self._stream.url if self._stream is not None else ""

    # ------------------------------------------------------------------ fetch
    def fetch_info(self, video_id: str, page: int) -> VideoInfo:
        payload = self.client.get_json(VIEW_URL, params=_id_params(video_id), headers=VIDEO_HEADERS)
        return parse_view(payload, video_id, page)

    def fetch_stream(self, info: VideoInfo) -> VideoStream:
        params = dict(_id_params(info.video_id))
        params.update({"cid": info.cid, "qn": 80, "fnval": 4048, "fourk": 1, "platform": "pc"})
        payload = self.client.get_json(PLAYURL_URL, params=params, headers=VIDEO_HEADERS)
        stream = choose_video_stream(parse_playurl_video(payload))
        if stream is None:
            raise StreamError("no playable stream in response")
        return stream

    def _refresh_if_due(self, video_id: str, page: int, now: float) -> VideoStream:
        expired = (now - self._fetched_at) > self.playurl_refresh_s
        if self._info is None or self._stream is None or expired:
            self._info = self.fetch_info(video_id, page)
            self._stream = self.fetch_stream(self._info)
            self._fetched_at = now
        return self._stream

    # -------------------------------------------------------------- measuring
    def measure(self, video_id: Optional[str] = None, page: Optional[int] = None) -> StreamMeasurement:
        video_id = video_id or self._video_id
        page = self._page if page is None else max(1, int(page))
        if not video_id:
            return StreamMeasurement(stream_ms=None, method="none", kind=KIND_VIDEO, error="no-video")
        try:
            stream = self._refresh_if_due(video_id, page, time.time())
            return self.measure_stream(stream)
        except (requests.RequestException, StreamError, ValueError, KeyError) as exc:
            self.invalidate()
            return StreamMeasurement(stream_ms=None, method="none", kind=KIND_VIDEO,
                                     error=_short(exc))

    def measure_stream(self, stream: VideoStream) -> StreamMeasurement:
        """Time a real ranged download from the CDN that serves this video."""
        headers = dict(VIDEO_HEADERS)
        headers["Range"] = f"bytes=0-{self.probe_bytes - 1}"
        started = time.perf_counter()
        response = self.client.session.get(
            stream.url, headers=headers, timeout=self.client.timeout_s, stream=True
        )
        try:
            response.raise_for_status()
            ttfb_ms = (time.perf_counter() - started) * 1000.0
            first_byte_at = time.perf_counter()
            received = 0
            for chunk in response.iter_content(chunk_size=32 * 1024):
                received += len(chunk)
                if received >= self.probe_bytes:
                    break
            download_s = max(1e-6, time.perf_counter() - first_byte_at)
        finally:
            response.close()

        if received <= 0:
            raise StreamError("empty response from CDN")

        throughput_mbps = (received * 8) / download_s / 1_000_000.0
        required_mbps = stream.required_mbps
        detail = {
            "ttfb_ms": ttfb_ms,
            "bytes": received,
            "download_ms": download_s * 1000.0,
            "quality": stream.quality,
            "codec": stream.codec,
            "dash": stream.is_dash,
            "status": response.status_code,
        }

        # One second of video at this quality, at the speed we just measured.
        if required_mbps and throughput_mbps > 0:
            first_second_ms = (required_mbps / throughput_mbps) * 1000.0
        else:
            # No bitrate advertised: fall back to the time the probe itself took.
            first_second_ms = download_s * 1000.0
            detail["bitrate_unknown"] = True

        info = self._info
        return StreamMeasurement(
            stream_ms=ttfb_ms + first_second_ms,
            method="video-startup",
            estimated=True,
            kind=KIND_VIDEO,
            buffer_ms=first_second_ms,
            throughput_mbps=throughput_mbps,
            required_mbps=required_mbps,
            host=stream.host,
            title=_title_for(info),
            detail=detail,
        )


def _title_for(info: Optional[VideoInfo]) -> str:
    if info is None:
        return ""
    if info.pages > 1 and info.part_title:
        return f"{info.title} - P{info.page} {info.part_title}"
    return info.title


def _short(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text[:200]
