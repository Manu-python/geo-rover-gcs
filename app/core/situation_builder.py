from __future__ import annotations

from app.core.experience import ExperienceSituation


def build_situation_from_telemetry(
    latest_telemetry: dict | None,
) -> ExperienceSituation:
    telemetry = dict(latest_telemetry or {})
    front_cm = _read_front_cm(telemetry.get("front_cm"))
    state = str(telemetry.get("state", "FRONT_UNKNOWN")).strip().upper()
    if state not in {"FRONT_CLEAR", "BLOCKED_FRONT", "FRONT_UNKNOWN"}:
        state = "FRONT_UNKNOWN"

    return ExperienceSituation(
        state=state,
        front_cm=front_cm,
        front_bucket=bucket_front_distance(front_cm),
        telemetry=telemetry,
    )


def bucket_front_distance(front_cm: float | None) -> str:
    if front_cm is None or front_cm == -1:
        return "unknown"
    if 0 <= front_cm < 15:
        return "very_close"
    if 15 <= front_cm < 30:
        return "near"
    if 30 <= front_cm < 60:
        return "medium"
    if front_cm >= 60:
        return "far"
    return "unknown"


def _read_front_cm(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
