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
    args = parser.parse_args()

    config = load_config(str(REPO_ROOT / "config" / "default.yaml"))
    allowed_commands = config.get("safety", {}).get("allowed_commands", [])
    command = validate_command(args.command, allowed_commands)

    esp32_config = config.get("esp32", {})
    client = ESP32UdpClient(
        host=str(esp32_config.get("host", "192.168.4.1")),
        port=int(esp32_config.get("port", 4210)),
        timeout_s=float(esp32_config.get("timeout_s", 2.0)),
    )

    try:
        reply = client.send_message(command)
    except Exception as exc:  # noqa: BLE001 - CLI should print readable failures.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
