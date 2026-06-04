from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryState:
    fl_cm: float | None
    fc_cm: float | None
    fr_cm: float | None
    l_cm: float | None
    r_cm: float | None
    state: str
    uptime_ms: int | None
    fw: str
    last_received_time: str


def telemetry_state_from_dict(
    telemetry: dict,
    last_received_time: str = "",
) -> TelemetryState:
    return TelemetryState(
        fl_cm=_optional_float(telemetry.get("fl_cm")),
        fc_cm=_optional_float(telemetry.get("fc_cm")),
        fr_cm=_optional_float(telemetry.get("fr_cm")),
        l_cm=_optional_float(telemetry.get("l_cm")),
        r_cm=_optional_float(telemetry.get("r_cm")),
        state=str(telemetry.get("state", "FRONT_UNKNOWN")).strip().upper(),
        uptime_ms=_optional_int(telemetry.get("uptime_ms")),
        fw=str(telemetry.get("fw", "")),
        last_received_time=last_received_time,
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
