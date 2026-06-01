from __future__ import annotations


MVP3_ALLOWED_COMMANDS = (
    "PING",
    "STATUS",
    "LED_ON",
    "LED_OFF",
    "LED_TOGGLE",
)

MVP9_MANUAL_COMMANDS = (
    "PING",
    "STATUS",
    "DIST",
    "LED_ON",
    "LED_OFF",
    "LED_TOGGLE",
    "SAFE_FWD",
    "FWD",
    "BACK",
    "LEFT",
    "RIGHT",
    "CW",
    "CCW",
    "STOP",
    "STREAM_ON",
    "STREAM_OFF",
)


def get_mvp3_allowed_commands() -> list[str]:
    """Return the simple string commands allowed during MVP 3."""
    return list(MVP3_ALLOWED_COMMANDS)


def get_mvp8_manual_commands() -> list[str]:
    """Return the operator-issued command strings allowed during MVP 8."""
    return get_mvp9_manual_commands()


def get_mvp9_manual_commands() -> list[str]:
    """Return the operator-issued command strings allowed during MVP 9."""
    return list(MVP9_MANUAL_COMMANDS)
