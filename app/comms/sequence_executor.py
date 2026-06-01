from __future__ import annotations

import time
from typing import Callable

from app.comms.esp32_udp_client import ESP32UdpClient
from app.core.movement_sequence import MovementSequence


class SequenceExecutor:
    """Execute a validated movement sequence on a worker thread."""

    def __init__(
        self,
        udp_client: ESP32UdpClient,
        log_callback: Callable[[str], None] | None = None,
        inter_step_delay_ms: int = 150,
    ):
        self.udp_client = udp_client
        self.log_callback = log_callback
        self.inter_step_delay_ms = int(inter_step_delay_ms)
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def execute_sequence(self, sequence: MovementSequence) -> None:
        for index, step in enumerate(sequence.steps, start=1):
            if self._cancel_requested:
                self._log("Sequence cancelled; sending STOP")
                self._send_stop_safely()
                return

            message = _format_step_message(step.command, step.duration_ms)
            self._log(
                f"Step {index}/{len(sequence.steps)}: sending {message} "
                f"({step.command} for {step.duration_ms} ms)"
            )

            try:
                reply = self.udp_client.send_message(
                    message,
                    ignore_prefixes=("TEL",),
                )
            except TimeoutError:
                self._log(
                    f"Step {index}: timeout waiting for {step.command}; "
                    "sending STOP"
                )
                self._send_stop_safely()
                raise
            except Exception:
                self._log(f"Step {index}: command failed; sending STOP")
                self._send_stop_safely()
                raise

            self._log(f"Step {index}: ESP32 reply: {reply}")

            if step.command == "STOP":
                self._log("STOP reached; sequence ended")
                return

            self._sleep_interruptibly(step.duration_ms + self.inter_step_delay_ms)

        self._log("Movement sequence complete")

    def _send_stop_safely(self) -> None:
        try:
            reply = self.udp_client.send_message("STOP", ignore_prefixes=("TEL",))
            self._log(f"STOP reply: {reply}")
        except Exception as exc:  # noqa: BLE001 - best-effort safety command.
            self._log(f"STOP send failed: {exc}")

    def _sleep_interruptibly(self, duration_ms: int) -> None:
        deadline = time.monotonic() + max(0, duration_ms) / 1000
        while not self._cancel_requested and time.monotonic() < deadline:
            time.sleep(min(0.05, deadline - time.monotonic()))

    def _log(self, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(message)


def _format_step_message(command: str, duration_ms: int) -> str:
    if command == "STOP":
        return "STOP"
    return f"{command},{duration_ms}"
