from __future__ import annotations

import requests


class OllamaClient:
    """Minimal Ollama HTTP API client for MVP 3 command selection."""

    def __init__(self, base_url: str, model: str, timeout_s: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = float(timeout_s)

    def check_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=self.timeout_s)
            return response.ok
        except requests.RequestException:
            return False

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ConnectionError(
                f"Ollama request failed at {self.base_url}: {exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(f"Ollama returned invalid JSON: {exc}") from exc

        return str(data.get("response", ""))
