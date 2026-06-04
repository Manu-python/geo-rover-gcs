from __future__ import annotations

from app.core.experience import ExperienceSituation


FINAL_TELEMETRY_STATES = {
    "CLEAR",
    "BLOCKED_FRONT",
    "BLOCKED_LEFT",
    "BLOCKED_RIGHT",
    "FRONT_UNKNOWN",
    "SENSOR_ERROR",
}


def build_situation_from_telemetry(
    latest_telemetry: dict | None,
) -> ExperienceSituation:
    telemetry = dict(latest_telemetry or {})
    fl_cm = _read_sensor_cm(telemetry.get("fl_cm"))
    fc_cm = _read_sensor_cm(telemetry.get("fc_cm"))
    fr_cm = _read_sensor_cm(telemetry.get("fr_cm"))
    l_cm = _read_sensor_cm(telemetry.get("l_cm"))
    r_cm = _read_sensor_cm(telemetry.get("r_cm"))

    legacy_front_cm = _read_sensor_cm(telemetry.get("front_cm"))
    front_cm = _minimum_valid_distance(
        value for value in (fl_cm, fc_cm, fr_cm, legacy_front_cm)
    )

    state = str(telemetry.get("state", "FRONT_UNKNOWN")).strip().upper()
    if state == "FRONT_CLEAR":
        state = "CLEAR"
    if state not in FINAL_TELEMETRY_STATES:
        state = "FRONT_UNKNOWN"

    return ExperienceSituation(
        state=state,
        front_cm=front_cm,
        fl_cm=fl_cm,
        fc_cm=fc_cm if fc_cm is not None else legacy_front_cm,
        fr_cm=fr_cm,
        l_cm=l_cm,
        r_cm=r_cm,
        front_bucket=bucket_distance(front_cm),
        left_bucket=bucket_distance(_valid_distance(l_cm)),
        right_bucket=bucket_distance(_valid_distance(r_cm)),
        telemetry=telemetry,
    )


def bucket_front_distance(front_cm: float | None) -> str:
    return bucket_distance(front_cm)


def bucket_distance(distance_cm: float | None) -> str:
    if distance_cm is None or distance_cm == -1:
        return "unknown"
    if 0 <= distance_cm < 15:
        return "very_close"
    if 15 <= distance_cm < 30:
        return "near"
    if 30 <= distance_cm < 60:
        return "medium"
    if distance_cm >= 60:
        return "far"
    return "unknown"


def _read_sensor_cm(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_distance(value: float | None) -> float | None:
    if value is None or value == -1:
        return None
    return value


def _minimum_valid_distance(values) -> float | None:
    valid_values = [
        value
        for value in values
        if value is not None and value >= 0
    ]
    if not valid_values:
        return None
    return min(valid_values)
