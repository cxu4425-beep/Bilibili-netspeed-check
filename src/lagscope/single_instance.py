"""One running copy per user, and a way to poke the running one.

Two people logged into the same PC each get their own instance because the
socket name contains the user name.

On Windows a named mutex is held alongside the socket. Nothing in the app
reads it: it exists so the *installer* can tell that the app is running.
Without it Windows refuses to replace a running executable and the setup
wizard reports "DeleteFile failed; code 5", which tells the person nothing
about what to do. With it, Inno Setup's ``AppMutex`` sees the app first and
asks them to close it.
"""

from __future__ import annotations

import getpass
import hashlib
import logging
import sys
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


# Must match AppMutex in packaging/installer.iss, or the installer learns
# nothing. Kept a plain constant for that reason - it is a shared contract.
WINDOWS_MUTEX_NAME = "LagScope-Running-Mutex"


def _claim_windows_mutex(name: str = WINDOWS_MUTEX_NAME):
    """Hold a named mutex for as long as the process lives, or None.

    Every failure is silent by design: this exists purely so an installer can
    notice us, and no part of the app should stop working because it could not
    be created.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes

        handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        return handle or None
    except Exception as exc:                      # noqa: BLE001 - never fatal
        LOG.debug("could not create the installer mutex: %s", exc)
        return None


class SingleInstance(QObject):
    """Server side of the guard; emits :attr:`activated` when poked."""

    activated = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._name = _socket_name()
        self._server: Optional[QLocalServer] = None
        # Held for the lifetime of the object; releasing it early would tell
        # an installer the app had exited while it is still running.
        self._mutex = _claim_windows_mutex()

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
        if self._mutex is not None:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._mutex)
            except Exception:                     # noqa: BLE001 - never fatal
                pass
            self._mutex = None
