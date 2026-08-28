"""Optional loopback bridge fed by the companion userscript.

The userscript in ``extras/bililagscope-bridge.user.js`` posts the address
of the page you are on to ``http://127.0.0.1:<port>/report``. That is the most
accurate source there is - it is the page itself talking - and it works in every
browser and every OS, at the cost of installing a userscript.

The server only ever binds the loopback interface, only accepts requests from
Bilibili origins, and only keeps the last reported URL in memory.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from ..models import WatchTarget
from .urls import target_from_url

LOG = logging.getLogger(__name__)

DEFAULT_PORT = 23124
MAX_BODY_BYTES = 8 * 1024
ALLOWED_ORIGINS = (
    "https://www.bilibili.com",
    "https://live.bilibili.com",
    "https://m.bilibili.com",
    "https://t.bilibili.com",
    "https://space.bilibili.com",
)


class _State:
    """Last report, shared between the server thread and the monitor."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._target: Optional[WatchTarget] = None

    def set(self, target: Optional[WatchTarget]) -> None:
        with self._lock:
            self._target = target

    def get(self) -> Optional[WatchTarget]:
        with self._lock:
            return self._target


def _make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "BiliLatencyBridge"

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - Qt-style override
            LOG.debug("bridge %s", fmt % args)

        # ------------------------------------------------------------- helpers
        def _origin_allowed(self) -> Optional[str]:
            origin = self.headers.get("Origin")
            if origin is None:
                return ""          # a userscript request without an Origin header
            return origin if origin in ALLOWED_ORIGINS else None

        def _send(self, status: int, payload: Optional[dict] = None, origin: str = "") -> None:
            body = json.dumps(payload or {}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        # ------------------------------------------------------------- methods
        def do_OPTIONS(self) -> None:  # noqa: N802 (http.server naming)
            origin = self._origin_allowed()
            if origin is None:
                self._send(403, {"error": "origin not allowed"})
                return
            self.send_response(204)
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            origin = self._origin_allowed()
            if origin is None:
                self._send(403, {"error": "origin not allowed"})
                return
            if self.path.rstrip("/") not in ("", "/status"):
                self._send(404, {"error": "not found"}, origin)
                return
            target = state.get()
            self._send(200, {
                "ok": True,
                "kind": target.kind if target else None,
                "ident": target.ident if target else None,
                "page": target.page if target else None,
            }, origin)

        def do_POST(self) -> None:  # noqa: N802
            origin = self._origin_allowed()
            if origin is None:
                self._send(403, {"error": "origin not allowed"}, "")
                return
            if self.path.rstrip("/") != "/report":
                self._send(404, {"error": "not found"}, origin)
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send(400, {"error": "bad length"}, origin)
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, {"error": "bad json"}, origin)
                return
            if not isinstance(payload, dict):
                self._send(400, {"error": "bad json"}, origin)
                return

            url = str(payload.get("url") or "")[:2048]
            title = str(payload.get("title") or "")[:300]
            target = target_from_url(url, title=title, source="bridge")
            if target is None:
                # Navigating away from a watchable page clears the target.
                state.set(None)
                self._send(200, {"ok": True, "watched": False}, origin)
                return
            state.set(target)
            self._send(200, {"ok": True, "watched": True, "kind": target.kind,
                             "ident": target.ident}, origin)

    return Handler


class BridgeServer:
    """Loopback HTTP endpoint; safe to start and stop repeatedly."""

    def __init__(self, port: int = DEFAULT_PORT, timeout_s: float = 120.0) -> None:
        self.port = int(port)
        self.timeout_s = float(timeout_s)
        self._state = _State()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> bool:
        if self._server is not None:
            return True
        try:
            server = ThreadingHTTPServer(("127.0.0.1", self.port), _make_handler(self._state))
        except OSError as exc:
            LOG.warning("bridge could not listen on 127.0.0.1:%s: %s", self.port, exc)
            return False
        server.daemon_threads = True
        server.timeout = 1.0
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="bili-bridge",
                                        kwargs={"poll_interval": 0.5}, daemon=True)
        self._thread.start()
        LOG.info("bridge listening on 127.0.0.1:%s", self.port)
        return True

    def stop(self) -> None:
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None
        self._state.set(None)

    def latest(self) -> Optional[WatchTarget]:
        """The last reported target, or ``None`` once it goes stale."""
        target = self._state.get()
        if target is None:
            return None
        if (time.time() - target.detected_at) > self.timeout_s:
            return None
        return target
