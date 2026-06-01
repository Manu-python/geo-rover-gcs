from __future__ import annotations

import json


def extract_sequence(llm_text: str) -> dict:
    """Extract and parse the first JSON object from LLM text."""
    text = str(llm_text).strip()
    if not text:
        raise ValueError("LLM output is empty; expected JSON")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as first_error:
        parsed = None
        last_error: json.JSONDecodeError | None = first_error
        for json_text in _iter_json_objects(text):
            try:
                parsed = json.loads(json_text)
                break
            except json.JSONDecodeError as exc:
                last_error = exc

        if parsed is None:
            detail = f": {last_error}" if last_error is not None else ""
            raise ValueError(f"No valid JSON object found in LLM output{detail}")

    if not isinstance(parsed, dict):
        raise ValueError("Movement sequence JSON must be an object")

    return parsed


def _iter_json_objects(text: str):
    start = text.find("{")
    while start != -1:
        candidate = _balanced_json_object_from(text, start)
        if candidate is not None:
            yield candidate
        start = text.find("{", start + 1)


def _balanced_json_object_from(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None
