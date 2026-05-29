from __future__ import annotations


MVP3_ALLOWED_COMMANDS = (
    "PING",
    "STATUS",
    "LED_ON",
    "LED_OFF",
    "LED_TOGGLE",
)


def get_mvp3_allowed_commands() -> list[str]:
    """Return the simple string commands allowed during MVP 3."""
    return list(MVP3_ALLOWED_COMMANDS)
