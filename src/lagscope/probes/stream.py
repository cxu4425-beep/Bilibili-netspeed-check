"""Server -> client probe for a Bilibili live room.

The public Bilibili web API hands out the same playback URLs the browser
player uses. This module asks for them, then measures how far behind the live
edge a player starting *right now* would be:

* HLS (fmp4/ts) with ``#EXT-X-PROGRAM-DATE-TIME``: the playlist carries the
  server's wall clock, so the delay is measured, not guessed.
* HLS without a date tag: the delay is derived from the playlist window.
* HTTP-FLV: the time until the first key frame arrives, i.e. how long the
  server's GOP cache plus the network makes a fresh viewer wait.

No login, cookie or token is used anywhere in this file.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse

import requests

from ..models import StreamMeasurement
from .network import HttpClient, tcp_rtt_ms

ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
PLAYURL_URL = "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo"

_ATTR_RE = re.compile(r'([A-Za-z0-9-]+)=("[^"]*"|[^,]*)')


class StreamError(RuntimeError):
    """A recoverable problem while talking to the live API."""


# --------------------------------------------------------------------- models
@dataclass(frozen=True)
class RoomInfo:
    room_id: str
    live_status: int = 0          # 0 offline, 1 live, 2 looping a recording
    title: str = ""
    uid: int = 0
    online: int = 0               # the "popularity" number the room shows
    area_name: str = ""
    parent_area_name: str = ""
    live_start: str = ""          # "YYYY-MM-DD HH:MM:SS", empty when offline

    @property
    def is_live(self) -> bool:
        return self.live_status == 1

    @property
    def area(self) -> str:
        parts = [part for part in (self.parent_area_name, self.area_name) if part]
        return " / ".join(parts)

    def live_seconds(self, now: Optional[float] = None) -> Optional[int]:
        """How long the stream has been up, from the room's start time."""
        if not self.live_start or self.live_start.startswith("0000"):
            return None
        try:
            started = datetime.strptime(self.live_start, "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            return None
        elapsed = (time.time() if now is None else now) - started
        return int(elapsed) if elapsed >= 0 else None


@dataclass(frozen=True)
class CdnLine:
    """One CDN edge this room is available on."""

    host: str
    rtt_ms: Optional[float] = None

    @property
    def reachable(self) -> bool:
        return self.rtt_ms is not None


@dataclass(frozen=True)
class StreamEndpoint:
    url: str
    protocol: str                 # http_hls | http_stream
    fmt: str                      # fmp4 | ts | flv
    codec: str = ""
    qn: int = 0

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or ""

    @property
    def is_hls(self) -> bool:
        return self.protocol == "http_hls"


@dataclass(frozen=True)
class HlsSegment:
    uri: str
    duration: float
    program_date_time: Optional[float] = None   # epoch seconds, server clock


@dataclass
class HlsPlaylist:
    target_duration: float = 0.0
    media_sequence: int = 0
    end_list: bool = False
    segments: list[HlsSegment] = field(default_factory=list)

    @property
    def window_s(self) -> float:
        return sum(seg.duration for seg in self.segments)

    @property
    def average_segment_s(self) -> float:
        if not self.segments:
            return self.target_duration
        return self.window_s / len(self.segments)

    def edge_epoch(self) -> Optional[float]:
        """Wall clock (server side) of the newest playable moment."""
        for index in range(len(self.segments) - 1, -1, -1):
            segment = self.segments[index]
            if segment.program_date_time is not None:
                trailing = sum(s.duration for s in self.segments[index:])
                return segment.program_date_time + trailing
        return None


# -------------------------------------------------------------------- parsing
def parse_program_date_time(value: str) -> Optional[float]:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def parse_m3u8(text: str, base_url: str = "") -> HlsPlaylist:
    """Parse the subset of the HLS playlist syntax a live edge actually uses."""
    playlist = HlsPlaylist()
    pending_duration: Optional[float] = None
    pending_pdt: Optional[float] = None
    saw_sequence = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-TARGETDURATION:"):
            playlist.target_duration = _to_float(line.split(":", 1)[1], 0.0)
        elif line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            playlist.media_sequence = int(_to_float(line.split(":", 1)[1], 0.0))
            saw_sequence = True
        elif line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            pending_pdt = parse_program_date_time(line.split(":", 1)[1])
        elif line.startswith("#EXTINF:"):
            payload = line.split(":", 1)[1].split(",", 1)[0]
            pending_duration = _to_float(payload, 0.0)
        elif line.startswith("#EXT-X-ENDLIST"):
            playlist.end_list = True
        elif line.startswith("#"):
            continue
        else:
            uri = urljoin(base_url, line) if base_url else line
            duration = pending_duration if pending_duration is not None else playlist.target_duration
            playlist.segments.append(HlsSegment(uri=uri, duration=duration, program_date_time=pending_pdt))
            pending_duration = None
            pending_pdt = None

    if not saw_sequence:
        playlist.media_sequence = 0
    return playlist


def _to_float(text: str, default: float) -> float:
    try:
        return float(text.strip())
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------- FLV bits
@dataclass(frozen=True)
class FlvTag:
    tag_type: int                 # 8 audio, 9 video, 18 script
    timestamp_ms: int
    is_keyframe: bool


class FlvTagParser:
    """Incremental HTTP-FLV parser that only looks at tag headers."""

    HEADER_SIZE = 9

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._header_done = False
        self._skip = 0

    def feed(self, chunk: bytes) -> Iterator[FlvTag]:
        self._buffer.extend(chunk)
        while True:
            if self._skip:
                take = min(self._skip, len(self._buffer))
                del self._buffer[:take]
                self._skip -= take
                if self._skip:
                    return
            if not self._header_done:
                if len(self._buffer) < self.HEADER_SIZE:
                    return
                if bytes(self._buffer[:3]) != b"FLV":
                    raise StreamError("not an FLV stream")
                data_offset = int.from_bytes(self._buffer[5:9], "big")
                self._skip = max(0, data_offset - self.HEADER_SIZE)
                del self._buffer[: self.HEADER_SIZE]
                self._header_done = True
                continue
            # 4 bytes previous tag size + 11 bytes tag header + 1 byte payload
            if len(self._buffer) < 16:
                return
            tag_type = self._buffer[4] & 0x1F
            data_size = int.from_bytes(self._buffer[5:8], "big")
            timestamp = int.from_bytes(self._buffer[8:11], "big") | (self._buffer[11] << 24)
            first_byte = self._buffer[15]
            is_keyframe = tag_type == 9 and (first_byte >> 4) == 1
            # Drop the 4-byte previous-tag-size and the 11-byte tag header,
            # then skip the payload we only peeked the first byte of.
            del self._buffer[:15]
            self._skip = data_size
            yield FlvTag(tag_type=tag_type, timestamp_ms=timestamp, is_keyframe=is_keyframe)


# --------------------------------------------------------------------- probe
class StreamProbe:
    """Resolves playback URLs for a room and measures the live-edge delay."""

    def __init__(self, client: HttpClient, *, prefer_hls: bool = True,
                 player_buffer_segments: float = 1.0, playurl_refresh_s: int = 240) -> None:
        self.client = client
        self.prefer_hls = prefer_hls
        self.player_buffer_segments = player_buffer_segments
        self.playurl_refresh_s = playurl_refresh_s
        self._room_id: str = ""
        self._endpoints: list[StreamEndpoint] = []
        self._endpoints_fetched_at: float = 0.0
        self._room_info: Optional[RoomInfo] = None
        self._clock_offset_ms: float = 0.0
        self._lines: list = []
        self._lines_checked_at = 0.0
        self._quality_desc: dict = {}

    # -------------------------------------------------------------- room data
    def set_room(self, room_id: str) -> None:
        if room_id != self._room_id:
            self._room_id = room_id
            self.invalidate()

    def invalidate(self) -> None:
        self._endpoints = []
        self._endpoints_fetched_at = 0.0
        self._room_info = None
        self._lines = []
        self._lines_checked_at = 0.0

    def set_clock_offset_ms(self, offset_ms: Optional[float]) -> None:
        if offset_ms is not None and abs(offset_ms) < 86_400_000:
            self._clock_offset_ms = offset_ms

    @property
    def room_info(self) -> Optional[RoomInfo]:
        return self._room_info

    def fetch_room_info(self, room_id: str) -> RoomInfo:
        payload = self.client.get_json(ROOM_INFO_URL, params={"room_id": room_id})
        if payload.get("code") != 0:
            raise StreamError(str(payload.get("message") or payload.get("msg") or "room info failed"))
        data = payload.get("data") or {}
        info = RoomInfo(
            room_id=str(data.get("room_id") or room_id),
            live_status=int(data.get("live_status") or 0),
            title=str(data.get("title") or ""),
            uid=int(data.get("uid") or 0),
            online=int(data.get("online") or 0),
            area_name=str(data.get("area_name") or ""),
            parent_area_name=str(data.get("parent_area_name") or ""),
            live_start=str(data.get("live_time") or ""),
        )
        self._room_info = info
        return info

    def fetch_endpoints(self, room_id: str) -> list[StreamEndpoint]:
        params = {
            "room_id": room_id,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1",
            "qn": 10000,
            "platform": "web",
            "ptype": 8,
            "dolby": 5,
            "panorama": 1,
        }
        payload = self.client.get_json(PLAYURL_URL, params=params)
        if payload.get("code") != 0:
            raise StreamError(str(payload.get("message") or payload.get("msg") or "playurl failed"))
        self._quality_desc = parse_quality_names(payload)
        endpoints = parse_playurl(payload)
        if not endpoints:
            raise StreamError("no playable stream in response")
        return endpoints

    def _endpoints_for(self, room_id: str, now: float) -> list[StreamEndpoint]:
        expired = (now - self._endpoints_fetched_at) > self.playurl_refresh_s
        if not self._endpoints or expired:
            self._endpoints = self.fetch_endpoints(room_id)
            self._endpoints_fetched_at = now
        return self._endpoints

    def choose_endpoint(self, endpoints: list[StreamEndpoint]) -> Optional[StreamEndpoint]:
        if not endpoints:
            return None
        hls = [e for e in endpoints if e.is_hls]
        flv = [e for e in endpoints if not e.is_hls]
        # fmp4 first: it is the only variant that reliably carries a date tag.
        hls.sort(key=lambda e: 0 if e.fmt == "fmp4" else 1)
        ordered = (hls + flv) if self.prefer_hls else (flv + hls)
        return ordered[0]

    # --------------------------------------------------------------- measuring
    def measure(self, room_id: Optional[str] = None) -> StreamMeasurement:
        room_id = room_id or self._room_id
        if not room_id:
            return StreamMeasurement(stream_ms=None, method="none", error="no-room")
        now = time.time()
        try:
            if self._room_info is None or (now - self._endpoints_fetched_at) > self.playurl_refresh_s:
                self.fetch_room_info(room_id)
            if self._room_info is not None and not self._room_info.is_live:
                return StreamMeasurement(stream_ms=None, method="none", error="offline")
            endpoints = self._endpoints_for(room_id, now)
        except (requests.RequestException, StreamError, ValueError) as exc:
            self.invalidate()
            return StreamMeasurement(stream_ms=None, method="none", error=_short(exc))

        endpoint = self.choose_endpoint(endpoints)
        if endpoint is None:
            return StreamMeasurement(stream_ms=None, method="none", error="no-endpoint")
        try:
            if endpoint.is_hls:
                return self.measure_hls(endpoint)
            return self.measure_flv(endpoint)
        except (requests.RequestException, StreamError, ValueError) as exc:
            # URLs expire; force a refresh before the next round.
            self.invalidate()
            return StreamMeasurement(stream_ms=None, method="none", host=endpoint.host, error=_short(exc))

    def measure_hls(self, endpoint: StreamEndpoint) -> StreamMeasurement:
        text, ttfb_ms, _ = self.client.get_text_timed(endpoint.url)
        received_at = time.time()
        playlist = parse_m3u8(text, base_url=endpoint.url)
        if not playlist.segments:
            raise StreamError("empty playlist")

        buffer_ms = playlist.average_segment_s * 1000.0 * max(0.0, self.player_buffer_segments)
        edge_epoch = playlist.edge_epoch()
        detail = {
            "ttfb_ms": ttfb_ms,
            "segments": len(playlist.segments),
            "target_duration_s": playlist.target_duration,
            "window_s": playlist.window_s,
            "media_sequence": playlist.media_sequence,
            "format": endpoint.fmt,
            "codec": endpoint.codec,
            "qn": endpoint.qn,
            "quality": self._quality_desc.get(endpoint.qn, ""),
        }

        if edge_epoch is not None:
            server_now = received_at + self._clock_offset_ms / 1000.0
            edge_lag_ms = max(0.0, (server_now - edge_epoch) * 1000.0)
            # A wildly wrong local clock shows up as an absurd lag; fall back.
            if edge_lag_ms < 600_000.0:
                return StreamMeasurement(
                    stream_ms=edge_lag_ms + buffer_ms + ttfb_ms,
                    method="hls-pdt",
                    estimated=False,
                    edge_lag_ms=edge_lag_ms,
                    buffer_ms=buffer_ms,
                    host=endpoint.host,
                    detail=detail,
                )
            detail["rejected_edge_lag_ms"] = edge_lag_ms

        # No usable server clock: the player has to fill the tail of the window.
        window_ms = (playlist.average_segment_s * (1.0 + max(0.0, self.player_buffer_segments))) * 1000.0
        return StreamMeasurement(
            stream_ms=window_ms + ttfb_ms,
            method="hls-window",
            estimated=True,
            edge_lag_ms=None,
            buffer_ms=buffer_ms,
            host=endpoint.host,
            detail=detail,
        )

    def measure_flv(self, endpoint: StreamEndpoint, budget_s: float = 8.0) -> StreamMeasurement:
        """Time how long a fresh viewer waits for the first displayable frame."""
        parser = FlvTagParser()
        started = time.perf_counter()
        ttfb_ms: Optional[float] = None
        first_keyframe_ms: Optional[float] = None
        first_tag_ts: Optional[int] = None
        keyframe_ts: Optional[int] = None
        response = self.client.session.get(endpoint.url, timeout=self.client.timeout_s, stream=True)
        try:
            response.raise_for_status()
            ttfb_ms = (time.perf_counter() - started) * 1000.0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                for tag in parser.feed(chunk):
                    if first_tag_ts is None:
                        first_tag_ts = tag.timestamp_ms
                    if tag.is_keyframe:
                        first_keyframe_ms = (time.perf_counter() - started) * 1000.0
                        keyframe_ts = tag.timestamp_ms
                        break
                if first_keyframe_ms is not None:
                    break
                if (time.perf_counter() - started) > budget_s:
                    break
        finally:
            response.close()

        if first_keyframe_ms is None:
            raise StreamError("no key frame within budget")
        detail = {
            "ttfb_ms": ttfb_ms,
            "first_tag_ts_ms": first_tag_ts,
            "keyframe_ts_ms": keyframe_ts,
            "format": endpoint.fmt,
        }
        return StreamMeasurement(
            stream_ms=first_keyframe_ms,
            method="flv-keyframe",
            estimated=True,
            edge_lag_ms=None,
            buffer_ms=None,
            host=endpoint.host,
            detail=detail,
        )

    def endpoint_rtt_ms(self, timeout_s: float = 4.0) -> Optional[float]:
        """TCP round trip to the CDN edge currently serving this room."""
        endpoint = self.choose_endpoint(self._endpoints)
        if endpoint is None:
            return None
        parsed = urlparse(endpoint.url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return tcp_rtt_ms(endpoint.host, port, timeout_s)

    def compare_lines(self, timeout_s: float = 4.0, max_hosts: int = 6) -> list:
        """Time every CDN edge this room is offered on, fastest first.

        Bilibili hands out several hosts for the same stream and the player just
        takes the first one; when that edge is slow, this is what shows it.
        """
        seen: dict = {}
        for endpoint in self._endpoints:
            host = endpoint.host
            if not host or host in seen:
                continue
            parsed = urlparse(endpoint.url)
            seen[host] = parsed.port or (443 if parsed.scheme == "https" else 80)
            if len(seen) >= max_hosts:
                break
        results = []
        for host, port in seen.items():
            results.append(CdnLine(host=host, rtt_ms=tcp_rtt_ms(host, port, timeout_s)))
        reachable = [line for line in results if line.rtt_ms is not None]
        unreachable = [line for line in results if line.rtt_ms is None]
        reachable.sort(key=lambda line: line.rtt_ms)
        self._lines = reachable + unreachable
        self._lines_checked_at = time.monotonic()
        return self._lines

    def lines_if_due(self, timeout_s: float = 4.0, interval_s: float = 60.0) -> list:
        """Refresh the line comparison at most once per ``interval_s``."""
        now = time.monotonic()
        if self._lines and (now - self._lines_checked_at) < interval_s:
            return self._lines
        return self.compare_lines(timeout_s)

    @property
    def current_host(self) -> str:
        endpoint = self.choose_endpoint(self._endpoints)
        return endpoint.host if endpoint else ""


def parse_quality_names(payload: dict) -> dict:
    """qn -> human name ("原画", "高清") from the playurl response."""
    names = {}
    data = payload.get("data") or {}
    for entry in (data.get("playurl_info") or {}).get("playurl", {}).get("g_qn_desc") or []:
        try:
            names[int(entry.get("qn"))] = str(entry.get("desc") or "")
        except (TypeError, ValueError):
            continue
    return names


def parse_playurl(payload: dict) -> list[StreamEndpoint]:
    """Flatten the nested playurl response into a list of playable URLs."""
    endpoints: list[StreamEndpoint] = []
    data = payload.get("data") or {}
    playurl = (data.get("playurl_info") or {}).get("playurl") or {}
    for stream in playurl.get("stream") or []:
        protocol = str(stream.get("protocol_name") or "")
        for fmt in stream.get("format") or []:
            fmt_name = str(fmt.get("format_name") or "")
            for codec in fmt.get("codec") or []:
                base_url = str(codec.get("base_url") or "")
                qn = int(codec.get("current_qn") or 0)
                codec_name = str(codec.get("codec_name") or "")
                for url_info in codec.get("url_info") or []:
                    host = str(url_info.get("host") or "")
                    extra = str(url_info.get("extra") or "")
                    if not host or not base_url:
                        continue
                    endpoints.append(
                        StreamEndpoint(
                            url=f"{host}{base_url}{extra}",
                            protocol=protocol,
                            fmt=fmt_name,
                            codec=codec_name,
                            qn=qn,
                        )
                    )
    return endpoints


def _short(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text[:200]
