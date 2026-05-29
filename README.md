# Geo Ground Control Station

Geo GCS is the Python/PyQt5 desktop ground control station for Geo, a small ESP32-S3 rover. The GCS is responsible for operator input, local LLM interaction through Ollama, deterministic command validation, UDP command routing, and logs.

MVP 3 proves one narrow path: a natural-language prompt is sent to Ollama, the model selects one allowed LED/status command, the GCS extracts and validates that command, and the ESP32 receives the validated UDP command.

The LLM never controls raw motors or hardware. For MVP 3, only these commands are allowed:

- `PING`
- `STATUS`
- `LED_ON`
- `LED_OFF`
- `LED_TOGGLE`

No motor control, sensor telemetry, autonomous navigation, obstacle avoidance, or raw motor commands are implemented in this MVP.

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install requirements:

```bash
pip install -r requirements.txt
```

## Run The App

```bash
python main.py
```

The app opens the Geo Ground Control Station window with ESP32 connection info, manual command buttons, an LLM prompt input, and a log panel.

## Direct UDP Test

Use this when you want to test Wi-Fi and firmware without Ollama or the PyQt5 UI:

```bash
python tools/send_udp_command.py PING
python tools/send_udp_command.py LED_ON
```

Expected examples:

- `PING` receives `PONG`
- `LED_ON` receives `OK:LED_ON`

## Ollama

Start Ollama:

```bash
ollama serve
```

Make sure the configured model is available:

```bash
ollama pull llama3.2
```

The model and base URL are configured in `config/default.yaml`:

```yaml
ollama:
  base_url: http://localhost:11434
  model: llama3.2
```

## LLM-To-LED Test

1. Start the ESP32 rover firmware and connect the laptop to the rover Wi-Fi.
2. Start Ollama and make sure the configured model is available.
3. Run `python main.py`.
4. Type `light up the room`.
5. Click `Ask LLM and Send`.

Expected result: the LLM chooses `LED_ON`, the GCS validates it, the ESP32 receives `LED_ON`, and the ESP32 replies `OK:LED_ON`.

If Ollama or the ESP32 is unavailable, the app reports the error in the log panel instead of crashing.
