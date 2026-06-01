# Geo Ground Control Station

Geo GCS is the Python/PyQt5 desktop ground control station for Geo, a small ESP32-S3 rover. The app handles operator commands, local Ollama prompting, deterministic command validation, UDP command routing, telemetry display, local experience memory, and logs.

MVP 10 adds retrieval-based experience memory while preserving MVP 8 telemetry and MVP 9 movement sequence generation/execution.

The GCS remains the deterministic middle layer. The LLM never controls raw motors, PWM values, or arbitrary hardware commands. The ESP32 remains the local safety, motor, and sensor executor.

## MVP 10 Experience Memory

An experience stores:

- robot situation and telemetry
- user instruction
- validated movement sequence
- outcome: `success`, `partial`, or `failure`
- optional notes
- timestamp

Experiences are stored locally as JSON Lines:

```text
data/experiences.jsonl
```

This is retrieval-based memory, not model training. Geo does not update LLM weights. The GCS reuses stored successful sequences when the current telemetry looks similar.

The saved situation is a pre-action telemetry snapshot. The GCS captures it when a movement sequence is generated and refreshes it immediately before executing the sequence. Clicking `Save Experience` later does not use post-action telemetry, because that would lose the obstacle state that made the action useful.

The GCS can also use feedback from the most recent trial in the next prompt. For example, if the sequence moved left enough but did not move forward enough, enter `LEFT was enough but SAFE_FWD was not enough` in Notes, set outcome to `partial`, then click `Use Notes As Feedback`. The next movement generation includes the previous sequence and feedback so the model can keep the left step similar and increase `SAFE_FWD` duration. This is prompt-based adaptation, not LLM training.

After LLM validation, the GCS also applies deterministic duration adjustments for simple feedback such as `not enough`, `too much`, or `enough`. The default adjustment is `200 ms`, clamped to the configured movement limits. Loading a remembered experience restores its notes and outcome and queues them for regeneration.

Similarity scoring is simple and rule-based:

- `+0.6` if robot state matches
- `+0.3` if front-distance bucket matches
- `+0.1` if the saved outcome is `success`

Only matches at or above `experience.min_similarity_score` are shown. Remembered sequences are loaded as the current validated sequence; the user must still click `Execute Validated Sequence`.

## Telemetry

The ESP32 firmware sends UDP packets like:

```text
TEL,front_cm=34.2,state=FRONT_CLEAR,uptime_ms=12345,fw=0.8.0-mvp8
```

The GCS displays front distance, robot state, uptime, firmware version, last telemetry timestamp, and telemetry connection status.

## Movement Sequences

Allowed LLM movement commands:

- `LEFT`
- `RIGHT`
- `BACK`
- `CW`
- `CCW`
- `SAFE_FWD`
- `STOP`

`FWD` is intentionally not allowed from the LLM. Forward intent must become `SAFE_FWD`, and the ESP32 firmware still enforces local safety.

When executing a validated movement sequence, the GCS sends duration-aware UDP payloads:

```text
LEFT,700
SAFE_FWD,1200
STOP
```

Manual buttons still send bare commands such as `LEFT` or `STOP`. Emergency stop always uses bare `STOP`.

## Setup

```bash
cd /Users/20265119/geo-rover-gcs
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start Ollama if you are using LLM features:

```bash
ollama serve
ollama pull llama3.2
```

Run the app:

```bash
python main.py
```

## Manual Command Test

Connect the laptop to the ESP32 AP, then run the app and click:

- `PING`, expected reply: `PONG`
- `DIST`, expected distance-related firmware reply
- `LEFT`, `RIGHT`, `BACK`, `CW`, `CCW`, `SAFE_FWD`, expected movement acknowledgements
- `STOP`, expected stop acknowledgement

Direct UDP command mode:

```bash
python tools/send_udp_command.py PING
python tools/send_udp_command.py LEFT
python tools/send_udp_command.py SAFE_FWD 1200
python tools/send_udp_command.py STOP
```

## Telemetry Test

1. Flash/run MVP 8 or newer firmware on the ESP32.
2. Connect the laptop to the ESP32 AP, expected SSID: `Geo-Rover`.
3. Run `python main.py`.
4. Click `Start Telemetry`.
5. Confirm telemetry fields update from incoming `TEL,...` packets.

## MVP 9 Movement Test

In `LLM Movement Sequence`:

1. Type `Dodge the obstacle by moving left first and then move forward.`
2. Click `Generate Movement Sequence`.
3. Confirm the validated sequence includes `LEFT` and `SAFE_FWD`.
4. Click `Execute Validated Sequence`.
5. Watch the execution log show each command and ESP32 reply.

## Feedback Adjustment Test

Use this when a sequence mostly works but needs tuning:

1. Execute a validated sequence.
2. In `Experience Memory`, set outcome to `partial`.
3. In Notes, type:
   ```text
   LEFT was enough but SAFE_FWD was not enough.
   ```
4. Click `Use Notes As Feedback`.
5. Click `Generate Movement Sequence` again with the same prompt.
6. Confirm the new sequence keeps `LEFT` similar and increases the `SAFE_FWD` duration, while still staying within configured safety limits.

Use `Clear Feedback` when you do not want the last trial to influence future generations.

## MVP 10 Memory Test

1. Start GCS.
2. Start telemetry.
3. Put an obstacle in front of Geo so state becomes `BLOCKED_FRONT`.
4. Type:
   ```text
   Dodge the obstacle by moving left first and then forward.
   ```
5. Click `Generate Movement Sequence`.
6. Click `Execute Validated Sequence`.
   The `Saved Situation` field should show the pre-action state, distance, and bucket.
7. If it works, set outcome to `success`.
8. Add optional notes.
9. Click `Save Experience`.
10. Put Geo in a similar `BLOCKED_FRONT` situation.
11. Click `Find Similar Experience`.
12. Confirm the previous `LEFT -> SAFE_FWD` sequence appears.
13. Click `Load Selected Experience Sequence`.
14. Click `Execute Validated Sequence` to approve execution.

Convenience flow:

```text
Find & Load Best Experience
```

This loads the best similar successful sequence but still does not execute automatically.

## Configuration

Default UDP, telemetry, movement, and memory settings live in `config/default.yaml`:

```yaml
movement:
  feedback_adjustment_ms: 200

experience:
  path: data/experiences.jsonl
  min_similarity_score: 0.6
  auto_execute: false
```

For MVP 10, `auto_execute` remains `false`.

If Ollama or the ESP32 is unavailable, the app reports readable errors in the log panel instead of crashing.
