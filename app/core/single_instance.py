"""Single-instance guard built on a named local socket.

Launching QuestPanel twice used to leave two identical always-on-top overlays
stacked on the desktop, neither obviously belonging to a particular process.
Now a second launch hands off to the first -- it raises the existing overlay
and exits -- which is also the behaviour you want when someone double-clicks
the launcher twice.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "QuestPanel.SingleInstance.v1"
_CONNECT_TIMEOUT_MS = 300
_SHOW = b"show\n"


class SingleInstance(QObject):
    """Owns the lock. :attr:`activated` fires when another launch is blocked."""

    activated = Signal()

    def __init__(self, name: str = SERVER_NAME, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Overridable so tests can use a private name and never collide with a
        # real QuestPanel the developer happens to have running.
        self.name = name
        self._server: QLocalServer | None = None
        self._probe: QLocalSocket | None = None

    def try_acquire(self) -> bool:
        """True if we are the first instance; False if another one answered."""
        # Parented to self so it is not garbage collected the moment this
        # method returns -- dropping the socket early tears the pipe down
        # before the running instance has read the payload.
        probe = QLocalSocket(self)
        probe.connectToServer(self.name)
        if probe.waitForConnected(_CONNECT_TIMEOUT_MS):
            probe.write(_SHOW)
            probe.flush()
            probe.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
            probe.disconnectFromServer()
            if probe.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                probe.waitForDisconnected(_CONNECT_TIMEOUT_MS)
            # Delivery is already guaranteed by the wait above, so the socket
            # can be closed now; the reference is kept only so its destruction
            # is tied to this object rather than happening at a random moment.
            probe.close()
            self._probe = probe
            return False
        probe.abort()
        probe.deleteLater()

        # No listener answered. A stale socket can survive a crash, so clear it
        # before binding -- otherwise the app could never start again.
        QLocalServer.removeServer(self.name)

        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self.name):
            # Losing the race is not fatal; run without the guard.
            return True
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._on_ready(socket))
        socket.disconnected.connect(socket.deleteLater)
        # The client writes and disconnects immediately, so its payload has
        # usually landed before this handler was attached -- readyRead already
        # fired and will not fire again. Drain whatever is buffered now.
        if socket.bytesAvailable() > 0:
            self._on_ready(socket)

    def _on_ready(self, socket: QLocalSocket) -> None:
        payload = bytes(socket.readAll())
        if not payload:
            return
        if _SHOW.strip() in payload.strip().splitlines():
            self.activated.emit()
        socket.disconnectFromServer()

    def release(self) -> None:
        """Close the listener and free the name.

        Deliberately no deleteLater() here: the server owns the accepted
        sockets, and scheduling its deletion while any of them were still
        pending deletion crashed the process.
        """
        if self._probe is not None:
            self._probe.close()
            self._probe = None
        if self._server is not None:
            try:
                self._server.newConnection.disconnect(self._on_connection)
            except (RuntimeError, TypeError):      # already disconnected
                pass
            self._server.close()
            QLocalServer.removeServer(self.name)
            self._server = None
