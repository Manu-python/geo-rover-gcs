# Geo Ground Control Station

Geo GCS is the Python/PyQt5 desktop application for Geo, an ESP32-S3 rover. It
provides operator controls, live telemetry, local Ollama prompting,
deterministic command validation, UDP routing, logs, and local experience
memory.

MVP 10 is complete. It adds retrieval-based experience memory while preserving
the MVP 8 telemetry workflow and the MVP 9 movement-sequence workflow.

## Safety Architecture

The GCS is the deterministic middle layer between the LLM and the rover:

```text
operator instruction and rover telemetry
    -> local Ollama model proposes a constrained sequence
    -> GCS extracts and validates every step
    -> operator approves execution
    -> GCS sends validated UDP commands
    -> ESP32 applies local safety checks and drives hardware
```

The LLM never sends raw motor values, wheel values, PWM values, or arbitrary
hardware commands. The ESP32 remains responsible for local motor control,
sensors, and forward-movement safety. Remembered actions are never executed
automatically in MVP 10.

## Current Scope

The current GCS supports:

- Manual UDP commands for connection checks, LEDs, movement, and telemetry
- Live front-distance telemetry with `FRONT_CLEAR`, `BLOCKED_FRONT`, and
  `FRONT_UNKNOWN` states
- Local Ollama generation of short movement sequences
- Deterministic validation before any LLM-proposed movement reaches the rover
- Duration-aware movement commands
- Local JSONL experience persistence
- Rule-based retrieval of similar past experiences
- Explicit operator approval before executing a remembered sequence
- Notes-based refinement of movement duration for later trials

This MVP does not include autonomous execution, cloud services, embeddings,
vector databases, model training, or experience-driven changes to LLM weights.

## Firmware Compatibility

The app expects the ESP32 access point and UDP command server to be available
at:

```text
SSID: Geo-Rover
ESP32 command endpoint: 192.168.4.1:4210
GCS telemetry listener: 0.0.0.0:4210
```

The firmware must support:

- Bare commands such as `PING`, `STOP`, `STREAM_ON`, and `STREAM_OFF`
- Timed movement commands such as `LEFT,700` and `SAFE_FWD,1200`
- Telemetry packets beginning with `TEL`
- `SAFE_FWD` as the locally safety-checked forward command

There is an important UDP routing detail. The GCS sends `STREAM_ON` from a
temporary UDP source port, but its telemetry listener is configured separately
on port `4210`. Firmware must send telemetry to the requesting laptop IP
address and the configured GCS telemetry port `4210`, not to the temporary
source port of the `STREAM_ON` packet.

## Setup

Create a virtual environment and install the Python dependencies:

```bash
cd path/to/geo-rover-gcs
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start Ollama in a separate terminal if using LLM features:

```bash
ollama serve
ollama pull llama3.2
```

The configured model can be changed in `config/default.yaml`.

Connect the laptop to the `Geo-Rover` Wi-Fi network, then launch the GCS:

```bash
source .venv/bin/activate
python main.py
```

## UI Workflow

### Manual Commands

Use the manual buttons to test firmware behavior without Ollama. These commands
still pass through the GCS allowlist.

Useful checks:

- `PING`, expected reply: `PONG`
- `DIST`, expected distance-related reply
- `LEFT`, `RIGHT`, `BACK`, `CW`, `CCW`, and `SAFE_FWD`, expected movement
  acknowledgement
- `STOP`, expected stop acknowledgement

Manual buttons send bare commands. The `STOP` button is the operator stop path.

### Telemetry

Click `Start Telemetry` to start the listener and send `STREAM_ON`. The UI
shows:

- front distance
- robot state
- uptime
- firmware version
- last telemetry timestamp
- telemetry connection status

Click `Stop Telemetry` to send `STREAM_OFF` and stop the listener. Telemetry can
be started again without restarting the app.

The expected packet format is:

```text
TEL,front_cm=34.2,state=FRONT_CLEAR,uptime_ms=12345,fw=0.9.0-mvp9
```

The `fw` value reports the installed firmware version and does not need to
match the GCS MVP number. Additional telemetry fields are preserved in saved
experience records.

### Legacy LED And Status Prompt

The retained `LLM Prompt` panel supports the earlier constrained command flow
for LEDs and status checks. It asks Ollama to select one allowed command,
validates that command, and sends it to the ESP32. Use `LLM Movement Sequence`
for the MVP 9 and MVP 10 movement workflow.

### LLM Movement Sequences

In `LLM Movement Sequence`, enter an instruction such as:

```text
Dodge the obstacle by moving left first and then move forward.
```

Click `Generate Movement Sequence`. The app asks Ollama for JSON, extracts the
JSON object, validates every step, and displays the validated result. It does
not execute the sequence yet.

Click `Execute Validated Sequence` to approve execution. The GCS sends each
step separately and logs the rover response.

Allowed LLM sequence commands:

- `LEFT`
- `RIGHT`
- `BACK`
- `CW`
- `CCW`
- `SAFE_FWD`
- `STOP`

`FWD` is intentionally rejected from LLM sequences. Forward intent must use
`SAFE_FWD`, allowing the ESP32 to enforce its local safety rule.

The current limits are:

- Maximum sequence length: `5` steps
- Movement duration range: `300-1500 ms`
- Default movement duration: `700 ms`
- Inter-step delay: `150 ms`
- `STOP` duration: `0 ms`

Do not remove these limits during MVP testing. They are part of the
deterministic safety boundary. Tune them deliberately in `config/default.yaml`
only after physical testing demonstrates a specific need.

## MVP 10 Experience Memory

### What Is Stored

An experience stores:

- a pre-action situation snapshot
- the complete telemetry dictionary
- the user instruction
- the validated movement steps and durations
- an outcome: `success`, `partial`, or `failure`
- optional operator notes
- an ID and timestamp

Records are appended locally as JSON Lines:

```text
data/experiences.jsonl
```

Example record:

```json
{"id":"example-id","timestamp":"2026-05-31T12:00:00-04:00","situation":{"state":"BLOCKED_FRONT","front_cm":8.5,"front_bucket":"very_close","telemetry":{"front_cm":8.5,"state":"BLOCKED_FRONT","fw":"0.9.0-mvp9"}},"user_instruction":"Move left and then forward to avoid the obstacle","sequence":[{"command":"LEFT","duration_ms":700},{"command":"SAFE_FWD","duration_ms":900}],"outcome":"success","notes":"LEFT was enough and SAFE_FWD was enough"}
```

The memory file is intentionally excluded from Git because it is local runtime
data. Back it up separately when trial history matters.

### Pre-Action Snapshots

Saved experiences use the situation before movement, not the telemetry after
the rover has completed the maneuver.

The GCS captures a snapshot when a movement sequence is generated and refreshes
it immediately before execution. Clicking `Save Experience` afterward stores
that snapshot. This preserves the obstacle distance and state that made the
action relevant.

Saving is rejected unless the GCS has:

- received telemetry
- captured a movement sequence
- captured a pre-action situation
- received a user instruction

### Similarity Matching

MVP 10 uses transparent rule-based scoring:

- `+0.6` if the robot state matches
- `+0.3` if the front-distance bucket matches
- `+0.1` if the stored outcome is `success`

Distance buckets:

- `unknown`: missing distance or `-1`
- `very_close`: `0 <= cm < 15`
- `near`: `15 <= cm < 30`
- `medium`: `30 <= cm < 60`
- `far`: `cm >= 60`

Only records scoring at least `0.6` are eligible. The UI displays all eligible
similar experiences, ordered by score. `Find & Load Best Experience` considers
successful records only.

### Saving An Experience

After executing a movement sequence:

1. Set the outcome to `success`, `partial`, or `failure`.
2. Add notes if useful.
3. Confirm that `Saved Situation` shows the intended pre-action state and
   distance.
4. Click `Save Experience`.

### Reusing An Experience

To reuse a stored action:

1. Recreate a similar rover situation.
2. Confirm telemetry is updating.
3. Click `Find Similar Experience`.
4. Select a matching record.
5. Click `Load Selected Experience Sequence`.
6. Review the loaded sequence.
7. Click `Execute Validated Sequence` to approve movement.

`Find & Load Best Experience` combines steps 3-5 for the highest-scoring
successful record. It still does not execute the sequence.

`experience.auto_execute` is reserved for future work and must remain `false`
for MVP 10.

## Notes-Based Refinement

Experience memory and feedback refinement are related but distinct:

- Loading an experience loads its saved sequence exactly as the next validated
  sequence.
- Loading an experience also restores its notes and queues them as feedback.
- Executing immediately runs the stored sequence unchanged.
- To produce an adjusted proposal, click `Generate Movement Sequence` after
  loading the experience or after clicking `Use Notes As Feedback`.

The next Ollama prompt receives the prior sequence, outcome, and notes. After
the LLM response is validated, the GCS also applies a deterministic duration
adjustment for simple operator feedback. The default adjustment is `200 ms`,
clamped to the configured duration limits.

Write notes that mention the relevant command or direction clearly:

```text
LEFT was enough but SAFE_FWD was not enough.
```

This keeps the previous `LEFT` duration similar and increases the `SAFE_FWD`
duration for the next generated proposal.

Supported feedback wording includes:

- Increase: `not enough`, `too short`, `increase`, `longer`, `more`,
  `further`, `farther`
- Decrease: `too much`, `too far`, `too long`, `decrease`, `shorter`, `less`,
  `overshot`
- Keep similar: `enough`, `good`, `correct`, `fine`, `worked`

Use `Clear Feedback` when the next generation should not use the previous
trial.

## Direct UDP Debugging

Use the CLI tool to test firmware communication without PyQt5 or Ollama:

```bash
python tools/send_udp_command.py PING
python tools/send_udp_command.py LEFT
python tools/send_udp_command.py SAFE_FWD 1200
python tools/send_udp_command.py STOP
```

Timed CLI commands use the same configured allowlist and duration limits as the
application.

## Acceptance Test

Use this flow after firmware or GCS changes:

1. Connect the laptop to `Geo-Rover`.
2. Launch the app and confirm manual `PING` returns `PONG`.
3. Click `Start Telemetry` and confirm fields update.
4. Click `Stop Telemetry`, then `Start Telemetry`, and confirm fields resume
   updating.
5. Place an obstacle in front of Geo and confirm `BLOCKED_FRONT`.
6. Generate and execute a `LEFT -> SAFE_FWD` sequence.
7. Confirm `Saved Situation` still shows the pre-action obstacle state.
8. Save the trial as `success`.
9. Restart the app.
10. Recreate the obstacle scenario and find similar experiences.
11. Load the saved record and confirm Geo does not move until clicking
    `Execute Validated Sequence`.
12. Run a `partial` trial with `SAFE_FWD was not enough`, regenerate, and
    confirm the proposed forward duration increases within configured limits.

## Configuration

Runtime settings live in `config/default.yaml`:

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
  max_steps: 5
  default_duration_ms: 700
  min_duration_ms: 300
  max_duration_ms: 1500
  feedback_adjustment_ms: 200
  inter_step_delay_ms: 150

experience:
  path: data/experiences.jsonl
  min_similarity_score: 0.6
  auto_execute: false

ollama:
  base_url: http://localhost:11434
  model: llama3.2
  timeout_s: 20
```

## Runtime Data Maintenance

Logs are written to timestamped files under `logs/`. Logs and local experience
records are excluded from Git.

To archive experience memory before a new test campaign:

```bash
mv data/experiences.jsonl data/experiences.backup.jsonl
```

The app creates a new `data/experiences.jsonl` automatically the next time an
experience is saved.

## Troubleshooting

### `PING` Does Not Return `PONG`

- Confirm the laptop is connected to `Geo-Rover`.
- Confirm the ESP32 is reachable at `192.168.4.1:4210`.
- Confirm the firmware UDP server is running.

### `STREAM_ON` Returns `OK:STREAM_ON`, But No Telemetry Appears

- Confirm the GCS telemetry status does not show a bind error.
- Confirm firmware sends telemetry to the laptop IP and fixed GCS telemetry
  port `4210`.
- Do not send telemetry to the temporary UDP source port used by the
  `STREAM_ON` command.
- Check ESP32 Serial logs for the telemetry destination.

### Telemetry Becomes Stale

The UI reports stale telemetry when no `TEL` packet arrives within
`telemetry.stale_timeout_s`. Confirm the rover is still connected and
streaming.

### Ollama Is Unavailable

Start Ollama and confirm the configured model exists:

```bash
ollama serve
ollama pull llama3.2
```

### A Remembered Sequence Ignores Its Notes

Loading a record restores the exact saved sequence. Click
`Generate Movement Sequence` afterward to generate an adjusted proposal using
the restored notes.

### Older Experiences Match Poorly

Records created before pre-action snapshot support may contain post-action
telemetry. Archive the old file and begin a clean trial set:

```bash
mv data/experiences.jsonl data/experiences.pre-snapshot-fix.jsonl
```

## Project Layout

```text
main.py                              PyQt5 entry point
config/default.yaml                  runtime configuration
app/ui/main_window.py                operator UI and workflow coordination
app/comms/esp32_udp_client.py        UDP command/reply client
app/comms/telemetry_receiver.py      non-blocking telemetry listener worker
app/comms/sequence_executor.py       validated sequence execution worker
app/core/telemetry_parser.py         TEL packet parser
app/core/sequence_validator.py       deterministic LLM sequence validator
app/core/sequence_feedback.py        deterministic notes-based refinement
app/core/experience.py               experience data model and serialization
app/core/experience_store.py         JSONL persistence and similarity search
app/core/situation_builder.py        telemetry snapshot and distance buckets
app/llm/movement_prompt_builder.py   constrained Ollama movement prompt
app/llm/sequence_extractor.py        defensive JSON extraction
tools/send_udp_command.py            direct UDP debugging CLI
```

If Ollama or the ESP32 is unavailable, the app reports readable errors in the
log panel instead of crashing.
