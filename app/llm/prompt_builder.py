from __future__ import annotations


def build_mvp3_prompt(user_prompt: str) -> str:
    return f"""You control Geo only by selecting exactly one command from:
LED_ON, LED_OFF, LED_TOGGLE, STATUS, PING.

Return only the command, no explanation, no markdown, no punctuation.

Examples:
"light up the room" -> LED_ON
"turn the light off" -> LED_OFF
"blink/change the light" -> LED_TOGGLE
"are you alive?" -> STATUS

User prompt:
"{user_prompt}"

Command:"""
