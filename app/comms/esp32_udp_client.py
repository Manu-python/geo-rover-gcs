from __future__ import annotations

import socket


class ESP32UdpClient:
    """Small UDP client for command/reply communication with the ESP32."""

    def __init__(self, host: str, port: int, timeout_s: float):
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)

    def send_message(self, message: str) -> str:
        payload = str(message).encode("utf-8")
        address = (self.host, self.port)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.sendto(payload, address)
                data, _addr = sock.recvfrom(4096)
        except socket.timeout as exc:
            raise TimeoutError(
                f"Timed out waiting for ESP32 reply from {self.host}:{self.port}"
            ) from exc
        except OSError as exc:
            raise ConnectionError(
                f"UDP socket error communicating with {self.host}:{self.port}: {exc}"
            ) from exc

        return data.decode("utf-8", errors="replace").strip()
