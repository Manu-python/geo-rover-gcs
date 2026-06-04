from __future__ import annotations


DISTANCE_FIELDS = ("fl_cm", "fc_cm", "fr_cm", "l_cm", "r_cm", "front_cm")
INTEGER_FIELDS = ("uptime_ms",)
TELEMETRY_STATES = (
    "CLEAR",
    "BLOCKED_FRONT",
    "BLOCKED_LEFT",
    "BLOCKED_RIGHT",
    "FRONT_UNKNOWN",
    "SENSOR_ERROR",
    # Legacy MVP 8 state kept readable for older firmware/logs.
    "FRONT_CLEAR",
)


def parse_telemetry_packet(text: str) -> dict:
    """Parse a Geo telemetry packet into typed fields."""
    packet = str(text).strip()
    if not packet:
        raise ValueError("Telemetry packet is empty")

    parts = [part.strip() for part in packet.split(",")]
    prefix = parts[0]
    if prefix != "TEL":
        return {}

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

        if key in DISTANCE_FIELDS:
            try:
                telemetry[key] = float(value)
            except ValueError as exc:
                raise ValueError(f"Invalid {key} value {value!r}") from exc
        elif key in INTEGER_FIELDS:
            try:
                telemetry[key] = int(value)
            except ValueError as exc:
                raise ValueError(f"Invalid {key} value {value!r}") from exc
        else:
            telemetry[key] = value

    return telemetry
