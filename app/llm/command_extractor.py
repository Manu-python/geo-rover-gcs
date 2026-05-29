from __future__ import annotations

import re


def extract_command(llm_text: str, allowed_commands: list[str]) -> str:
    """Extract a single allowed command from possibly messy LLM text."""
    normalized = str(llm_text).strip().upper()
    allowed = [str(command).strip().upper() for command in allowed_commands]

    if normalized in allowed:
        return normalized

    matches: list[str] = []
    for command in allowed:
        pattern = rf"\b{re.escape(command)}\b"
        if re.search(pattern, normalized):
            matches.append(command)

    unique_matches = sorted(set(matches))

    if len(unique_matches) == 1:
        return unique_matches[0]

    if not unique_matches:
        raise ValueError(
            f"No allowed command found in LLM output. Output was: {llm_text!r}"
        )

    raise ValueError(
        "Multiple conflicting commands found in LLM output: "
        f"{', '.join(unique_matches)}"
    )
