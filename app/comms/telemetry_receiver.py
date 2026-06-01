from __future__ import annotations

import socket
import threading
import time

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from app.core.telemetry_parser import parse_telemetry_packet


class TelemetryReceiver(QObject):
    """UDP telemetry listener intended to run in a QThread."""

    telemetry_received = pyqtSignal(dict)
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    packet_received = pyqtSignal(str)
    stale = pyqtSignal()
    stopped = pyqtSignal()

    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        expected_prefix: str = "TEL",
        stale_timeout_s: float = 2.0,
    ):
        super().__init__()
        self.listen_host = listen_host
        self.listen_port = int(listen_port)
        self.expected_prefix = expected_prefix
        self.stale_timeout_s = float(stale_timeout_s)
        self._stop_requested = threading.Event()
        self._socket: socket.socket | None = None

    @pyqtSlot()
    def run(self) -> None:
        last_packet_at = time.monotonic()
        stale_emitted = False

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.listen_host, self.listen_port))
            self._socket.settimeout(0.2)
            self.status_changed.emit(
                f"Listening on {self.listen_host}:{self.listen_port}"
            )

            while not self._stop_requested.is_set():
                try:
                    data, _addr = self._socket.recvfrom(4096)
                except socket.timeout:
                    if (
                        not stale_emitted
                        and time.monotonic() - last_packet_at > self.stale_timeout_s
                    ):
                        self.stale.emit()
                        stale_emitted = True
                    continue
                except OSError as exc:
                    if not self._stop_requested.is_set():
                        self.error_occurred.emit(f"Telemetry socket error: {exc}")
                    break

                text = data.decode("utf-8", errors="replace").strip()
                if not text:
                    continue

                if not text.startswith(self.expected_prefix):
                    continue

                self.packet_received.emit(text)
                try:
                    telemetry = parse_telemetry_packet(text)
                except ValueError as exc:
                    self.error_occurred.emit(f"Telemetry parse error: {exc}")
                    continue

                last_packet_at = time.monotonic()
                stale_emitted = False
                self.telemetry_received.emit(telemetry)
        except OSError as exc:
            self.error_occurred.emit(
                f"Could not start telemetry listener on "
                f"{self.listen_host}:{self.listen_port}: {exc}"
            )
        finally:
            if self._socket is not None:
                self._socket.close()
                self._socket = None
            self.stopped.emit()

    @pyqtSlot()
    def stop(self) -> None:
        self.request_stop()

    def request_stop(self) -> None:
        """Request shutdown from any thread without waiting for Qt events."""
        self._stop_requested.set()
        if self._socket is not None:
            self._socket.close()
