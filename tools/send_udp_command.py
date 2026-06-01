from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.comms.esp32_udp_client import ESP32UdpClient  # noqa: E402
from app.core.config_loader import load_config  # noqa: E402
from app.core.safety_validator import validate_command  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one validated UDP command to Geo.")
    parser.add_argument("command", help="Command to send, for example LED_ON")
    parser.add_argument(
        "duration_ms",
        nargs="?",
        type=int,
        help="Optional movement duration, for example: SAFE_FWD 1200",
    )
    args = parser.parse_args()

    config = load_config(str(REPO_ROOT / "config" / "default.yaml"))
    try:
        allowed_commands = config.get("safety", {}).get("allowed_commands", [])
        command = validate_command(args.command, allowed_commands)
        message = command

        if args.duration_ms is not None:
            _validate_timed_command(command, args.duration_ms, config)
            message = "STOP" if command == "STOP" else f"{command},{args.duration_ms}"
    except Exception as exc:  # noqa: BLE001 - CLI should print readable failures.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    esp32_config = config.get("esp32", {})
    client = ESP32UdpClient(
        host=str(esp32_config.get("host", "192.168.4.1")),
        port=int(esp32_config.get("port", 4210)),
        timeout_s=float(esp32_config.get("timeout_s", 2.0)),
    )

    try:
        reply = client.send_message(message, ignore_prefixes=("TEL",))
    except Exception as exc:  # noqa: BLE001 - CLI should print readable failures.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(reply)
    return 0


def _validate_timed_command(command: str, duration_ms: int, config: dict) -> None:
    movement_config = config.get("movement", {})
    allowed_timed_commands = {
        str(item).strip().upper()
        for item in movement_config.get("allowed_sequence_commands", [])
    }
    if command not in allowed_timed_commands:
        raise ValueError(
            f"Timed command '{command}' is not allowed. "
            f"Allowed timed commands: {', '.join(sorted(allowed_timed_commands))}"
        )

    if command == "STOP":
        if duration_ms != 0:
            raise ValueError("STOP duration must be 0 ms")
        return

    min_duration_ms = int(movement_config.get("min_duration_ms", 300))
    max_duration_ms = int(movement_config.get("max_duration_ms", 1500))
    if duration_ms < min_duration_ms or duration_ms > max_duration_ms:
        raise ValueError(
            f"Duration {duration_ms} ms is outside "
            f"{min_duration_ms}-{max_duration_ms} ms"
        )


if __name__ == "__main__":
    raise SystemExit(main())
