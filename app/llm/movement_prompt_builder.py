from __future__ import annotations

from app.core.movement_sequence import MovementSequence


def build_mvp9_movement_prompt(
    user_prompt: str,
    latest_telemetry: dict | None,
    previous_sequence: MovementSequence | None = None,
    trial_feedback: str | None = None,
    trial_outcome: str | None = None,
) -> str:
    telemetry_lines = ["Latest telemetry: unavailable"]
    if latest_telemetry:
        telemetry_lines = [
            "Latest telemetry:",
            f"- state: {latest_telemetry.get('state', 'unknown')}",
            f"- fl_cm: {latest_telemetry.get('fl_cm', 'unknown')}",
            f"- fc_cm: {latest_telemetry.get('fc_cm', latest_telemetry.get('front_cm', 'unknown'))}",
            f"- fr_cm: {latest_telemetry.get('fr_cm', 'unknown')}",
            f"- l_cm: {latest_telemetry.get('l_cm', 'unknown')}",
            f"- r_cm: {latest_telemetry.get('r_cm', 'unknown')}",
        ]

    telemetry_block = "\n".join(telemetry_lines)
    feedback_block = _build_feedback_block(
        previous_sequence=previous_sequence,
        trial_feedback=trial_feedback,
        trial_outcome=trial_outcome,
    )

    return f"""Geo is a mecanum rover.
You control Geo only by selecting a short sequence of commands from:
LEFT, RIGHT, BACK, CW, CCW, SAFE_FWD, STOP.

Return only valid JSON.
Do not use markdown.
Do not explain.
Do not use raw motor values.
Do not use FWD; use SAFE_FWD instead.
Use at most 5 steps.
Use duration_ms between 300 and 1500 for movement commands.
Use duration_ms 0 for STOP.

Sensor context rules:
- fl_cm, fc_cm, fr_cm are front-left, front-center, and front-right distance sensors.
- l_cm and r_cm are side distance sensors.
- A value of -1 means that sensor is unavailable.
- If state is BLOCKED_FRONT, use LEFT, RIGHT, BACK, CW, or CCW before SAFE_FWD.
- If the left sensor is blocked or l_cm is low, avoid LEFT.
- If the right sensor is blocked or r_cm is low, avoid RIGHT.
- If both sides are blocked, prefer BACK, CW, or CCW.
- If state is CLEAR and front sensors are clear, SAFE_FWD is okay.

{telemetry_block}

{feedback_block}

Example:
User: Dodge the obstacle by moving left first and then go forward
Telemetry: state=BLOCKED_FRONT, l_cm=60, r_cm=20
JSON:
{{"sequence":[{{"command":"LEFT","duration_ms":700}},{{"command":"SAFE_FWD","duration_ms":900}}]}}

Example:
User: Avoid the obstacle.
Telemetry: state=BLOCKED_FRONT, l_cm=12, r_cm=65
JSON:
{{"sequence":[{{"command":"RIGHT","duration_ms":700}},{{"command":"SAFE_FWD","duration_ms":900}}]}}

Example:
User: Back up and turn right
Telemetry: state=CLEAR, l_cm=62, r_cm=55
JSON:
{{"sequence":[{{"command":"BACK","duration_ms":700}},{{"command":"CW","duration_ms":500}}]}}

User:
{user_prompt}

JSON:"""


def _build_feedback_block(
    previous_sequence: MovementSequence | None,
    trial_feedback: str | None,
    trial_outcome: str | None,
) -> str:
    feedback = (trial_feedback or "").strip()
    outcome = (trial_outcome or "").strip()
    if previous_sequence is None and not feedback and not outcome:
        return "Previous trial feedback: unavailable"

    lines = ["Previous trial feedback:"]
    if previous_sequence is not None:
        lines.append("- previous_sequence:")
        for step in previous_sequence.steps:
            lines.append(f"  - {step.command} for {step.duration_ms} ms")

    if outcome:
        lines.append(f"- outcome: {outcome}")
    if feedback:
        lines.append(f"- operator_notes: {feedback}")

    lines.extend(
        [
            "- Adapt the next sequence using the operator notes.",
            "- If a movement was enough, keep that command and duration similar.",
            "- If a movement was not enough, increase that command's duration within the allowed range.",
            "- If forward was not enough, increase SAFE_FWD duration; never use FWD.",
            "- If a movement was too much, reduce that command's duration within the allowed range.",
        ]
    )
    return "\n".join(lines)
