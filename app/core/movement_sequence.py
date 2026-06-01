from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MovementStep:
    command: str
    duration_ms: int


@dataclass(frozen=True)
class MovementSequence:
    steps: list[MovementStep]
