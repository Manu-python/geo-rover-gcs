from __future__ import annotations

import re

from app.core.movement_sequence import MovementSequence, MovementStep


INCREASE_TERMS = (
    "not enough",
    "too short",
    "increase",
    "longer",
    "more",
    "further",
    "farther",
)
DECREASE_TERMS = (
    "too much",
    "too far",
    "too long",
    "decrease",
    "shorter",
    "less",
    "overshot",
)
KEEP_TERMS = ("enough", "good", "correct", "fine", "worked")

COMMAND_ALIASES = {
    "SAFE_FWD": ("safe_fwd", "safe fwd", "forward", "move forward", "go forward"),
    "LEFT": ("left",),
    "RIGHT": ("right",),
    "BACK": ("back", "backward", "back up"),
    "CW": ("cw", "clockwise", "turn right"),
    "CCW": ("ccw", "counterclockwise", "turn left"),
}


def adjust_sequence_from_feedback(
    sequence: MovementSequence,
    feedback: str,
    config: dict,
    previous_sequence: MovementSequence | None = None,
) -> tuple[MovementSequence, list[str]]:
    """Apply simple operator duration feedback after LLM validation."""
    notes = str(feedback).strip().lower()
    if not notes:
        return sequence, []

    movement_config = config.get("movement", {})
    min_duration_ms = int(movement_config.get("min_duration_ms", 300))
    max_duration_ms = int(movement_config.get("max_duration_ms", 1500))
    adjustment_ms = int(movement_config.get("feedback_adjustment_ms", 200))
    prior_durations = _prior_durations(previous_sequence)

    adjusted_steps: list[MovementStep] = []
    messages: list[str] = []

    for step in sequence.steps:
        if step.command == "STOP":
            adjusted_steps.append(step)
            continue

        direction = _feedback_direction(step.command, notes)
        baseline = _take_prior_duration(prior_durations, step.command, step.duration_ms)
        duration_ms = step.duration_ms

        if direction == "increase":
            duration_ms = max(duration_ms, baseline + adjustment_ms)
        elif direction == "decrease":
            duration_ms = min(duration_ms, baseline - adjustment_ms)
        elif direction == "keep":
            duration_ms = baseline

        duration_ms = min(max(duration_ms, min_duration_ms), max_duration_ms)
        adjusted_steps.append(
            MovementStep(command=step.command, duration_ms=duration_ms)
        )

        if duration_ms != step.duration_ms:
            messages.append(
                f"Feedback adjusted {step.command}: "
                f"{step.duration_ms} -> {duration_ms} ms"
            )

    return MovementSequence(steps=adjusted_steps), messages


def _feedback_direction(command: str, notes: str) -> str | None:
    for clause in re.split(r"[.;\n]|\bbut\b", notes):
        if not _clause_mentions_command(clause, command):
            continue
        if any(term in clause for term in INCREASE_TERMS):
            return "increase"
        if any(term in clause for term in DECREASE_TERMS):
            return "decrease"
        if any(term in clause for term in KEEP_TERMS):
            return "keep"
    return None


def _clause_mentions_command(clause: str, command: str) -> bool:
    aliases = COMMAND_ALIASES.get(command, (command.lower(),))
    return any(alias in clause for alias in aliases)


def _prior_durations(
    previous_sequence: MovementSequence | None,
) -> dict[str, list[int]]:
    durations: dict[str, list[int]] = {}
    if previous_sequence is None:
        return durations

    for step in previous_sequence.steps:
        durations.setdefault(step.command, []).append(step.duration_ms)
    return durations


def _take_prior_duration(
    prior_durations: dict[str, list[int]],
    command: str,
    default_duration_ms: int,
) -> int:
    durations = prior_durations.get(command, [])
    if not durations:
        return default_duration_ms
    return durations.pop(0)
