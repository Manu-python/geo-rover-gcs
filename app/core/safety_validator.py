from __future__ import annotations


def validate_command(command: str, allowed_commands: list[str]) -> str:
    """Normalize and validate a command against the allowlist."""
    normalized = " ".join(str(command).strip().split()).upper()
    allowed = {str(item).strip().upper() for item in allowed_commands}

    if normalized in allowed:
        return normalized

    raise ValueError(
        f"Command '{normalized}' is not allowed. "
        f"Allowed commands: {', '.join(sorted(allowed))}"
    )
