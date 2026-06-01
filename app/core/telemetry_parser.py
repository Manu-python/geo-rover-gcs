from __future__ import annotations


TELEMETRY_STATES = ("FRONT_CLEAR", "BLOCKED_FRONT", "FRONT_UNKNOWN")


def parse_telemetry_packet(text: str) -> dict:
    """Parse a Geo telemetry packet into typed fields."""
    packet = str(text).strip()
    if not packet:
        raise ValueError("Telemetry packet is empty")

    parts = [part.strip() for part in packet.split(",")]
    prefix = parts[0]
    if prefix != "TEL":
        raise ValueError(f"Telemetry packet must start with TEL, got {prefix!r}")

    telemetry: dict = {}
    for part in parts[1:]:
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Invalid telemetry field {part!r}")

        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid telemetry field {part!r}")

        if key == "front_cm":
            try:
                telemetry[key] = float(value)
            except ValueError as exc:
                raise ValueError(f"Invalid front_cm value {value!r}") from exc
        elif key == "uptime_ms":
            try:
                telemetry[key] = int(value)
            except ValueError as exc:
                raise ValueError(f"Invalid uptime_ms value {value!r}") from exc
        else:
            telemetry[key] = value

    return telemetry
