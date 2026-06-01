from __future__ import annotations

from app.core.movement_sequence import MovementSequence, MovementStep


RAW_CONTROL_KEYS = {
    "motor",
    "motors",
    "pwm",
    "speed",
    "wheel",
    "wheels",
    "fl",
    "fr",
    "rl",
    "rr",
    "front_left",
    "front_right",
    "rear_left",
    "rear_right",
}


def validate_movement_sequence(
    data: dict,
    config: dict,
    latest_telemetry: dict | None = None,
) -> MovementSequence:
    """Validate LLM-generated movement JSON before anything reaches the rover."""
    if not isinstance(data, dict):
        raise ValueError("Movement sequence JSON must be an object")

    if "sequence" not in data:
        raise ValueError("Movement sequence JSON must contain a 'sequence' field")

    sequence_data = data["sequence"]
    if not isinstance(sequence_data, list):
        raise ValueError("'sequence' must be a list")

    movement_config = config.get("movement", {})
    allowed_commands = {
        str(command).strip().upper()
        for command in movement_config.get("allowed_sequence_commands", [])
    }
    max_steps = int(movement_config.get("max_steps", 5))
    default_duration_ms = int(movement_config.get("default_duration_ms", 700))
    min_duration_ms = int(movement_config.get("min_duration_ms", 300))
    max_duration_ms = int(movement_config.get("max_duration_ms", 1500))

    if not sequence_data:
        raise ValueError("Movement sequence cannot be empty")

    if len(sequence_data) > max_steps:
        raise ValueError(
            f"Movement sequence has {len(sequence_data)} steps; max is {max_steps}"
        )

    telemetry_state = None
    if latest_telemetry:
        telemetry_state = str(latest_telemetry.get("state", "")).strip().upper()

    steps: list[MovementStep] = []
    for index, raw_step in enumerate(sequence_data, start=1):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Step {index} must be an object")

        _reject_raw_motor_fields(raw_step, index)

        unknown_keys = set(raw_step) - {"command", "duration_ms"}
        if unknown_keys:
            raise ValueError(
                f"Step {index} contains unsupported fields: "
                f"{', '.join(sorted(unknown_keys))}"
            )

        if "command" not in raw_step:
            raise ValueError(f"Step {index} is missing 'command'")

        command = str(raw_step["command"]).strip().upper()
        if command == "FWD":
            raise ValueError("FWD is not allowed in MVP 9; use SAFE_FWD instead")

        if command not in allowed_commands:
            allowed_text = ", ".join(sorted(allowed_commands))
            raise ValueError(
                f"Step {index} command '{command}' is not allowed. "
                f"Allowed commands: {allowed_text}"
            )

        duration_ms = _parse_duration_ms(
            raw_step=raw_step,
            index=index,
            command=command,
            default_duration_ms=default_duration_ms,
        )

        if command == "STOP":
            if duration_ms != 0:
                raise ValueError("STOP duration must be 0 ms")
        elif duration_ms < min_duration_ms or duration_ms > max_duration_ms:
            raise ValueError(
                f"Step {index} duration {duration_ms} ms is outside "
                f"{min_duration_ms}-{max_duration_ms} ms"
            )

        if telemetry_state == "BLOCKED_FRONT" and command == "SAFE_FWD":
            # SAFE_FWD stays allowed. The ESP32 firmware is still the local safety gate.
            pass

        steps.append(MovementStep(command=command, duration_ms=duration_ms))

    return MovementSequence(steps=steps)


def _reject_raw_motor_fields(raw_step: dict, index: int) -> None:
    for key in raw_step:
        key_text = str(key).strip().lower()
        if key_text in RAW_CONTROL_KEYS or "pwm" in key_text or "motor" in key_text:
            raise ValueError(f"Step {index} contains raw motor field '{key}'")


def _parse_duration_ms(
    raw_step: dict,
    index: int,
    command: str,
    default_duration_ms: int,
) -> int:
    if "duration_ms" not in raw_step:
        return 0 if command == "STOP" else default_duration_ms

    duration = raw_step["duration_ms"]
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise ValueError(f"Step {index} duration_ms must be an integer")

    return duration
