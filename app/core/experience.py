from __future__ import annotations

from dataclasses import dataclass

from app.core.movement_sequence import MovementStep


@dataclass(frozen=True)
class ExperienceSituation:
    state: str
    front_cm: float | None
    fl_cm: float | None
    fc_cm: float | None
    fr_cm: float | None
    l_cm: float | None
    r_cm: float | None
    front_bucket: str
    left_bucket: str
    right_bucket: str
    telemetry: dict


@dataclass(frozen=True)
class ExperienceRecord:
    id: str
    timestamp: str
    situation: ExperienceSituation
    user_instruction: str
    sequence: list[MovementStep]
    outcome: str
    notes: str


def experience_record_to_dict(record: ExperienceRecord) -> dict:
    return {
        "id": record.id,
        "timestamp": record.timestamp,
        "situation": {
            "state": record.situation.state,
            "front_cm": record.situation.front_cm,
            "fl_cm": record.situation.fl_cm,
            "fc_cm": record.situation.fc_cm,
            "fr_cm": record.situation.fr_cm,
            "l_cm": record.situation.l_cm,
            "r_cm": record.situation.r_cm,
            "front_bucket": record.situation.front_bucket,
            "left_bucket": record.situation.left_bucket,
            "right_bucket": record.situation.right_bucket,
            "telemetry": record.situation.telemetry,
        },
        "user_instruction": record.user_instruction,
        "sequence": [
            {"command": step.command, "duration_ms": step.duration_ms}
            for step in record.sequence
        ],
        "outcome": record.outcome,
        "notes": record.notes,
    }


def experience_record_from_dict(data: dict) -> ExperienceRecord:
    situation_data = data.get("situation", {})
    legacy_front_cm = _optional_float(situation_data.get("front_cm"))
    situation = ExperienceSituation(
        state=str(situation_data.get("state", "FRONT_UNKNOWN")),
        front_cm=legacy_front_cm,
        fl_cm=_optional_float(situation_data.get("fl_cm")),
        fc_cm=_optional_float(situation_data.get("fc_cm")),
        fr_cm=_optional_float(situation_data.get("fr_cm")),
        l_cm=_optional_float(situation_data.get("l_cm")),
        r_cm=_optional_float(situation_data.get("r_cm")),
        front_bucket=str(situation_data.get("front_bucket", "unknown")),
        left_bucket=str(situation_data.get("left_bucket", "unknown")),
        right_bucket=str(situation_data.get("right_bucket", "unknown")),
        telemetry=dict(situation_data.get("telemetry", {})),
    )

    sequence = []
    for step in data.get("sequence", []):
        sequence.append(
            MovementStep(
                command=str(step.get("command", "")).strip().upper(),
                duration_ms=int(step.get("duration_ms", 0)),
            )
        )

    return ExperienceRecord(
        id=str(data.get("id", "")),
        timestamp=str(data.get("timestamp", "")),
        situation=situation,
        user_instruction=str(data.get("user_instruction", "")),
        sequence=sequence,
        outcome=str(data.get("outcome", "")).strip().lower(),
        notes=str(data.get("notes", "")),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
