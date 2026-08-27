"""One running copy per user, and a way to poke the running one.

Two people logged into the same PC each get their own instance because the
socket name contains the user name.
"""

from __future__ import annotations

import getpass
import hashlib
import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import APP_ID

LOG = logging.getLogger(__name__)


def _socket_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - exotic environments
        user = "default"
    digest = hashlib.sha1(user.encode("utf-8", "replace")).hexdigest()[:10]
    return f"{APP_ID}-{digest}"


class SingleInstance(QObject):
    """Server side of the guard; emits :attr:`activated` when poked."""

    activated = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._name = _socket_name()
        self._server: Optional[QLocalServer] = None

    def notify_running_instance(self, timeout_ms: int = 300) -> bool:
        """Return True when another instance answered (so this one may exit)."""
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return True

    def listen(self) -> bool:
        QLocalServer.removeServer(self._name)  # clean up after a crash
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        if not self._server.listen(self._name):
            LOG.warning("single-instance server failed: %s", self._server.errorString())
            return False
        return True

    def _on_connection(self) -> None:
        assert self._server is not None
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self.activated.emit())
        socket.disconnected.connect(socket.deleteLater)

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
