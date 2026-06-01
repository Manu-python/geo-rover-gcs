from __future__ import annotations

import socket
import time


class ESP32UdpClient:
    """Small UDP client for command/reply communication with the ESP32."""

    def __init__(self, host: str, port: int, timeout_s: float):
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)

    def send_message(
        self,
        message: str,
        ignore_prefixes: tuple[str, ...] = (),
    ) -> str:
        payload = str(message).encode("utf-8")
        address = (self.host, self.port)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                deadline = time.monotonic() + self.timeout_s
                sock.sendto(payload, address)

                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout

                    sock.settimeout(remaining)
                    data, _addr = sock.recvfrom(4096)
                    reply = data.decode("utf-8", errors="replace").strip()

                    if _should_ignore_reply(reply, ignore_prefixes):
                        continue

                    return reply
        except socket.timeout as exc:
            raise TimeoutError(
                f"Timed out waiting for ESP32 reply from {self.host}:{self.port}"
            ) from exc
        except OSError as exc:
            raise ConnectionError(
                f"UDP socket error communicating with {self.host}:{self.port}: {exc}"
            ) from exc


def _should_ignore_reply(reply: str, ignore_prefixes: tuple[str, ...]) -> bool:
    return any(reply.startswith(prefix) for prefix in ignore_prefixes)
