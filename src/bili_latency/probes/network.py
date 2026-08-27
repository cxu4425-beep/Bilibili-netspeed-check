"""Network-level probes: TCP round trip, HTTP time-to-first-byte, clock offset."""

from __future__ import annotations

import email.utils
import socket
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

from ..models import NetworkMeasurement

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://live.bilibili.com/",
    "Origin": "https://live.bilibili.com",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def host_port_from_url(url: str, default_port: int = 443) -> Tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else default_port)
    return host, port


def tcp_rtt_ms(host: str, port: int = 443, timeout_s: float = 4.0) -> Optional[float]:
    """Time a TCP handshake, which is one round trip to the edge server.

    Returns ``None`` when the host is unreachable within ``timeout_s``.
    """
    if not host:
        return None
    started = time.perf_counter()
    sock = None
    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout_s)
        elapsed = (time.perf_counter() - started) * 1000.0
        return elapsed
    except (OSError, ValueError):
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def clock_offset_ms(server_date_header: str, local_recv_epoch: float, rtt_ms: Optional[float]) -> Optional[float]:
    """Estimate ``server_clock - local_clock`` from an HTTP ``Date`` header.

    The header only has one-second resolution, so the result carries roughly
    +/-500 ms of quantisation error. It is good enough to keep a wall-clock
    stream measurement from drifting when the user's clock is minutes off.
    """
    if not server_date_header:
        return None
    try:
        server_epoch = email.utils.parsedate_to_datetime(server_date_header).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    one_way_ms = (rtt_ms or 0.0) / 2.0
    return (server_epoch - local_recv_epoch) * 1000.0 + one_way_ms


class HttpClient:
    """Small wrapper around :class:`requests.Session` with timing helpers.

    A single session is reused so keep-alive connections make repeated probes
    cheap; :meth:`recycle` drops the pool after a network change.
    """

    def __init__(self, timeout_s: float = 4.0) -> None:
        self.timeout_s = timeout_s
        self._session = self._new_session()

    @staticmethod
    def _new_session() -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        session.trust_env = True  # honour the user's proxy settings
        return session

    @property
    def session(self) -> requests.Session:
        return self._session

    def recycle(self) -> None:
        self.close()
        self._session = self._new_session()

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:  # pragma: no cover - defensive, close must never raise
            pass

    def get_json(self, url: str, params: Optional[dict] = None,
                 headers: Optional[dict] = None) -> dict:
        response = self._session.get(url, params=params, headers=headers, timeout=self.timeout_s)
        response.raise_for_status()
        return response.json()

    def get_text_timed(self, url: str) -> Tuple[str, float, requests.Response]:
        """GET a small text body; returns ``(text, ttfb_ms, response)``."""
        started = time.perf_counter()
        response = self._session.get(url, timeout=self.timeout_s, stream=True)
        ttfb_ms = (time.perf_counter() - started) * 1000.0
        try:
            response.raise_for_status()
            text = response.text
        finally:
            response.close()
        return text, ttfb_ms, response

    def measure(self, url: str, rtt_ms: Optional[float] = None) -> NetworkMeasurement:
        """Measure TTFB (and clock offset) for a URL, plus a TCP RTT if absent."""
        host, port = host_port_from_url(url)
        if rtt_ms is None:
            rtt_ms = tcp_rtt_ms(host, port, self.timeout_s)
        try:
            started = time.perf_counter()
            response = self._session.get(url, timeout=self.timeout_s, stream=True)
            ttfb_ms = (time.perf_counter() - started) * 1000.0
            recv_epoch = time.time()
            date_header = response.headers.get("Date", "")
            response.close()
        except requests.RequestException as exc:
            return NetworkMeasurement(rtt_ms=rtt_ms, host=host, error=_short_error(exc))
        return NetworkMeasurement(
            rtt_ms=rtt_ms,
            ttfb_ms=ttfb_ms,
            host=host,
            clock_offset_ms=clock_offset_ms(date_header, recv_epoch, rtt_ms),
        )


def _short_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text[:200]
