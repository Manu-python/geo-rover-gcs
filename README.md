# Geo Ground Control Station

Geo GCS is the Python/PyQt5 desktop ground control station for Geo, an
AI-assisted adaptive rover. The final rover uses an ESP32-S3, two DRV8833 motor
drivers, four TT motors with mecanum wheels, and five VL53L0X Time-of-Flight
sensors.

The GCS handles telemetry display, local Ollama prompting, natural-language to
movement-sequence generation, deterministic validation, sequence execution,
local experience memory, logging, and operator approval before execution.

The ESP32 firmware handles motor execution, local movement safety, ToF sensor
readings, UDP command receiving, UDP telemetry streaming, and Wi-Fi AP mode.

## Safety Architecture

The LLM does not directly control motors. It only proposes high-level movement
commands from a fixed allowlist. The GCS validates every proposed command and
duration before sending anything to the ESP32. The ESP32 still enforces
real-time local safety with its sensors.

```text
operator instruction + latest telemetry
    -> local Ollama prompt
    -> strict JSON movement sequence
    -> GCS extraction and validation
    -> operator approval
    -> UDP commands to ESP32
    -> ESP32 local safety + motor execution
```

Remembered sequences are not auto-executed in MVP 10/final-ToF GCS. The user
must explicitly click `Execute Validated Sequence`.

## Current Capabilities

- Manual UDP command buttons
- Start/stop live telemetry streaming
- Five ToF sensor distance display
- Robot state display
- LLM movement sequence generation
- Deterministic movement validation
- Duration-aware sequence execution
- STOP/cancel support
- Local JSONL experience memory
- Similar-experience retrieval using five-sensor context
- Notes-based feedback for later sequence generation

This project does not use cloud services, embeddings, a vector database, or LLM
weight training.

## Setup

```bash
cd /path/to/geo-rover-gcs
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start Ollama in a separate terminal if using LLM features:

```bash
ollama serve
ollama pull llama3.2
```

Connect the laptop to the rover Wi-Fi AP:

```text
SSID: Geo-Rover
ESP32 command endpoint: 192.168.4.1:4210
```

Run the GCS:

```bash
source .venv/bin/activate
python main.py
```

## Final Telemetry Format

The final ToF firmware sends UDP telemetry packets like:

```text
TEL,fl_cm=45.2,fc_cm=38.1,fr_cm=41.7,l_cm=62.0,r_cm=55.4,state=CLEAR,uptime_ms=12345,fw=0.11.0-final-tof
```

If a sensor is unavailable, the firmware sends `-1` for that sensor:

```text
TEL,fl_cm=-1,fc_cm=18.0,fr_cm=-1,l_cm=-1,r_cm=54.0,state=BLOCKED_FRONT,uptime_ms=12345,fw=0.11.0-final-tof
```

Field meanings:

- `fl_cm`: front-left distance
- `fc_cm`: front-center distance
- `fr_cm`: front-right distance
- `l_cm`: left distance
- `r_cm`: right distance
- `state`: firmware state classification
- `uptime_ms`: ESP32 uptime
- `fw`: firmware version

Supported states:

- `CLEAR`
- `BLOCKED_FRONT`
- `BLOCKED_LEFT`
- `BLOCKED_RIGHT`
- `FRONT_UNKNOWN`
- `SENSOR_ERROR`

The GCS displays `-1.0 cm (unavailable)` for missing sensors and does not crash
when one or more sensor fields are unavailable.

## Telemetry Workflow

1. Upload the final ToF firmware to the ESP32.
2. Connect the laptop to `Geo-Rover`.
3. Start the GCS with `python main.py`.
4. Press `PING` and verify `PONG`.
5. Press `Start Telemetry`.
6. Confirm all five sensor labels update:
   - Front Left
   - Front Center
   - Front Right
   - Left
   - Right
7. Put an obstacle in front and confirm `BLOCKED_FRONT`.
8. Put an obstacle on the left and confirm the left distance/state changes.
9. Press `Stop Telemetry`, then `Start Telemetry`, and confirm telemetry resumes.

The GCS listens on:

```yaml
telemetry:
  listen_host: 0.0.0.0
  listen_port: 4210
```

Firmware should send telemetry to the laptop IP and the configured telemetry
port `4210`. It should not stream to the temporary UDP source port used by the
`STREAM_ON` command.

## Manual Commands

Manual buttons are for testing firmware behavior without Ollama:

- `PING`
- `STATUS`
- `DIST`
- `STREAM_ON`
- `STREAM_OFF`
- `FWD`
- `SAFE_FWD`
- `BACK`
- `LEFT`
- `RIGHT`
- `CW`
- `CCW`
- `STOP`

`FWD` is manual/test only. It may appear as `FWD (manual/test)` in the UI.
LLM-generated sequences are not allowed to use `FWD`.

Direct UDP debugging without the GUI:

```bash
python tools/send_udp_command.py PING
python tools/send_udp_command.py SAFE_FWD 1200
python tools/send_udp_command.py STOP
```

Timed commands use the same configured movement duration limits as the UI.

## LLM Movement Command Policy

Allowed LLM sequence commands:

- `LEFT`
- `RIGHT`
- `BACK`
- `CW`
- `CCW`
- `SAFE_FWD`
- `STOP`

Rejected from LLM sequences:

- `FWD`
- raw motor values
- raw PWM values
- wheel-specific commands
- unknown command names

Movement limits:

- Maximum steps: `5`
- Default movement duration: `700 ms`
- Minimum movement duration: `300 ms`
- Maximum movement duration: `1500 ms`
- Inter-step delay: `150 ms`
- `STOP` duration: `0 ms`

Telemetry-aware validation:

- `LEFT` is rejected if `state=BLOCKED_LEFT` or `l_cm` is below
  `side_block_threshold_cm`.
- `RIGHT` is rejected if `state=BLOCKED_RIGHT` or `r_cm` is below
  `side_block_threshold_cm`.
- `SAFE_FWD` remains allowed when front is blocked because the ESP32 is the
  local safety gate, but the GCS shows a warning if the sequence tries forward
  before an escape step.
- If telemetry is unavailable or reports `FRONT_UNKNOWN`/`SENSOR_ERROR`, the
  GCS allows validation but shows a warning.

## LLM Movement Test

1. Start telemetry.
2. Put an obstacle in front of Geo.
3. Confirm telemetry shows `BLOCKED_FRONT`.
4. Enter:
   ```text
   Dodge the obstacle by moving left first and then forward.
   ```
5. Click `Generate Movement Sequence`.
6. Confirm the validated sequence uses `LEFT` and `SAFE_FWD`.
7. Click `Execute Validated Sequence` to approve execution.
8. Watch the execution log for each UDP command and ESP32 response.

If the left side is blocked, the validator should reject `LEFT`. If the right
side is blocked, it should reject `RIGHT`.

## Experience Memory

Experience memory is stored locally in:

```text
data/experiences.jsonl
```

This is retrieval-based memory, not model training. The robot does not modify
LLM weights. The GCS stores successful or partially successful situation/action
pairs and retrieves similar records later.

An experience stores:

- pre-action robot state
- five sensor values
- front, left, and right distance buckets
- complete telemetry dictionary
- user instruction
- validated movement sequence
- outcome: `success`, `partial`, or `failure`
- notes
- timestamp

Distance buckets:

- `unknown`: missing value or `-1`
- `very_close`: `0 <= cm < 15`
- `near`: `15 <= cm < 30`
- `medium`: `30 <= cm < 60`
- `far`: `cm >= 60`

For `front_bucket`, the GCS uses the minimum valid front distance from
`fl_cm`, `fc_cm`, and `fr_cm`. `left_bucket` uses `l_cm`. `right_bucket` uses
`r_cm`.

Similarity scoring:

- `+0.45` if state matches
- `+0.20` if front bucket matches
- `+0.15` if left bucket matches
- `+0.15` if right bucket matches
- `+0.05` if outcome is `success`

Only matches at or above `experience.min_similarity_score` are shown. The
default result cap is `experience.max_results: 3`.

Example JSONL record:

```json
{"id":"example-id","timestamp":"2026-06-03T12:00:00-04:00","situation":{"state":"BLOCKED_FRONT","front_cm":8.5,"fl_cm":12.0,"fc_cm":8.5,"fr_cm":16.0,"l_cm":64.0,"r_cm":22.0,"front_bucket":"very_close","left_bucket":"far","right_bucket":"near","telemetry":{"fl_cm":12.0,"fc_cm":8.5,"fr_cm":16.0,"l_cm":64.0,"r_cm":22.0,"state":"BLOCKED_FRONT","fw":"0.11.0-final-tof"}},"user_instruction":"Dodge the obstacle by moving left first and then forward.","sequence":[{"command":"LEFT","duration_ms":700},{"command":"SAFE_FWD","duration_ms":900}],"outcome":"success","notes":"LEFT was enough and SAFE_FWD was enough"}
```

## Experience Memory Test

1. Start telemetry.
2. Put an obstacle in front of Geo and confirm `BLOCKED_FRONT`.
3. Enter:
   ```text
   Dodge the obstacle by moving left first and then forward.
   ```
4. Click `Generate Movement Sequence`.
5. Click `Execute Validated Sequence`.
6. Confirm `Saved Situation` shows the pre-action sensor values and buckets.
7. Set outcome to `success`.
8. Add notes if useful.
9. Click `Save Experience`.
10. Recreate a similar five-sensor situation.
11. Click `Find Similar Experience`.
12. Select the remembered record.
13. Click `Load Selected Experience Sequence`.
14. Review the loaded sequence.
15. Click `Execute Validated Sequence` to approve movement.

`Find & Load Best Experience` loads the best successful match but still does
not execute it.

## Notes-Based Refinement

Notes can guide the next LLM generation and deterministic duration adjustment.
For example:

```text
LEFT was enough but SAFE_FWD was not enough.
```

Then click `Use Notes As Feedback` and generate again. The next prompt includes
the previous sequence and notes. After validation, the GCS also applies a
simple deterministic duration adjustment, clamped to the configured movement
limits.

Use `Clear Feedback` when the next generation should ignore the last trial.

## Configuration

Main settings live in `config/default.yaml`:

```yaml
esp32:
  host: 192.168.4.1
  port: 4210
  timeout_s: 2.0

telemetry:
  listen_host: 0.0.0.0
  listen_port: 4210
  expected_prefix: TEL
  stale_timeout_s: 2.0

movement:
  allowed_sequence_commands:
    - LEFT
    - RIGHT
    - BACK
    - CW
    - CCW
    - SAFE_FWD
    - STOP
  max_steps: 5
  default_duration_ms: 700
  min_duration_ms: 300
  max_duration_ms: 1500
  inter_step_delay_ms: 150
  side_block_threshold_cm: 15.0
  front_block_threshold_cm: 20.0

experience:
  path: data/experiences.jsonl
  min_similarity_score: 0.6
  max_results: 3
  auto_execute: false
```

For this MVP, keep `experience.auto_execute` set to `false`.

## Troubleshooting

### `PING` Does Not Return `PONG`

- Confirm the laptop is connected to `Geo-Rover`.
- Confirm the ESP32 command endpoint is `192.168.4.1:4210`.
- Confirm the firmware UDP command server is running.

### `STREAM_ON` Replies OK But Telemetry Is Stale

- Confirm the telemetry listener is not showing a bind error.
- Confirm firmware sends telemetry to the laptop IP and port `4210`.
- Check ESP32 Serial logs for the telemetry destination.
- Confirm firewall settings are not blocking UDP on the laptop.

### One Sensor Shows `-1`

`-1` means the firmware reported that sensor as unavailable. The GCS displays
it and treats its bucket as `unknown`.

### Ollama Is Unreachable

Run:

```bash
ollama serve
ollama pull llama3.2
```

Also confirm `ollama.base_url` and `ollama.model` in `config/default.yaml`.

### A Remembered Sequence Does Not Use Notes Immediately

Loading an experience loads the saved sequence exactly. To use its notes as
feedback for a new proposal, click `Generate Movement Sequence` after loading
the experience.

## Runtime Data

Logs are written under `logs/`. Experience records are written under `data/`.
Both are local runtime data and should not be committed.

The `Delete All Experiences` button in the Experience Memory tab removes the
local `data/experiences.jsonl` memory file after confirmation and clears the
visible match list. It does not delete logs and does not change the currently
validated movement sequence.

To archive a test campaign:

```bash
mv data/experiences.jsonl data/experiences.tof-test-backup.jsonl
```

The app creates a new memory file on the next save.

## Project Layout

```text
main.py                              PyQt5 entry point
config/default.yaml                  runtime configuration
app/ui/main_window.py                operator UI and workflow coordination
app/comms/esp32_udp_client.py        UDP command/reply client
app/comms/telemetry_receiver.py      UDP telemetry listener worker
app/comms/sequence_executor.py       validated sequence execution worker
app/core/telemetry_parser.py         TEL packet parser
app/core/telemetry_state.py          five-sensor telemetry state model
app/core/sequence_validator.py       deterministic LLM sequence validator
app/core/sequence_feedback.py        notes-based duration refinement
app/core/experience.py               experience data model
app/core/experience_store.py         JSONL persistence and similarity search
app/core/situation_builder.py        telemetry-to-situation conversion
app/llm/movement_prompt_builder.py   constrained movement prompt
app/llm/sequence_extractor.py        defensive JSON extraction
tools/send_udp_command.py            direct UDP debugging CLI
```
