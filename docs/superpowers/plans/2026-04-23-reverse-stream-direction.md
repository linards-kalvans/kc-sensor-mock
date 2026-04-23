# Reverse Stream Direction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reverse the transport roles so the mock sensor becomes a TCP producer client that connects outward to a consumer server and immediately streams fixed-size binary records with no handshake.

**Architecture:** Keep the binary record contract, sample generator, and ring buffer intact. Replace the current listener-and-send transport with two explicit runtime roles: a producer client that generates/buffers/sends records, and a consumer server that accepts one producer connection and reads exact 632-byte records for validation and optional capture. Rename modules and CLI entry points around producer/consumer semantics so the architecture matches the real deployment model instead of the old server/client terminology.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, standard library `socket`, `threading`, `argparse`, `tomllib`, `struct`, and existing package modules.

---

## Design Decisions

### 1. Keep the binary record contract unchanged
- **Why:** The flaw is connection direction, not payload design. Preserving `<HHIIQQiii296H` avoids needless connector churn and keeps the C migration path intact.
- **Contract:** Producer sends repeated 632-byte records immediately after TCP connection establishment. No handshake, framing, delimiter, or checksum is introduced.

### 2. Replace ambiguous server/client naming with producer/consumer naming
- **Why:** Current names encode wrong mental model. Reversing behavior under old names would create long-term confusion in code, docs, and tests.
- **Decision:** Introduce `producer.py` and `consumer.py`. Remove or thin-wrapper old `server.py`/`client.py` only if needed during migration, but final public API should use producer/consumer terminology.

### 3. Keep ring buffer on producer side
- **Why:** Ring buffer semantics still fit real sensor behavior: data is produced continuously, outbound network link may lag, oldest buffered data is dropped first.
- **Decision:** Producer thread generates records into ring buffer. Sender thread drains buffer to connected consumer server.

### 4. Keep single-connection model
- **Why:** Confirmed scope still matches one sensor to one consumer endpoint. Multiple simultaneous consumer connections are still out of scope.
- **Decision:** Producer maintains at most one active TCP connection to configured consumer endpoint. If disconnected, it reconnects and resumes streaming newest buffered records.

### 5. Move exact-byte capture to producer send path
- **Why:** Capture requirement is “exact bytes transmitted.” That truth lives on sender side.
- **Decision:** Producer capture writes bytes immediately before socket send and rolls back on send failure, preserving current trust model.

### 6. Make consumer server a validation/reference tool, not core producer runtime
- **Why:** Real architecture needs a listening consumer. Repo still benefits from a built-in sink for connector testing and end-to-end tests.
- **Decision:** Consumer server accepts one producer, reads exact records, validates stream progression, and can optionally persist raw bytes.

## File-by-File Plan

### Files to keep with minimal or no logic change
- `src/kc_sensor_mock/protocol.py`
  - Keep record schema, encoding/decoding, constants, scaling helpers.
- `src/kc_sensor_mock/generator.py`
  - Keep `RecordGenerator.next_record(dropped_records_total: int) -> SensorRecord`.
- `src/kc_sensor_mock/ring_buffer.py`
  - Keep drop-oldest FIFO behavior.
- `src/kc_sensor_mock/sample_data.py`
  - No transport-specific change.
- `src/kc_sensor_mock/config.py`
  - Rework config fields but keep validation style.

### Files to replace or substantially rewrite
- `src/kc_sensor_mock/producer.py` **(new)**
  - `class SensorProducerClient:`
    - `__init__(self, config: MockConfig) -> None`
    - `start(self) -> None`
    - `stop(self) -> None`
    - internal `_produce()`, `_connect_and_stream()`, `_stream_to_socket(sock)`, `_write_capture_payload(payload)`, `_rollback_capture_payload(position)`
  - Owns generator, ring buffer, reconnect loop, producer-side capture.

- `src/kc_sensor_mock/consumer.py` **(new)**
  - `recv_exact(sock: socket.socket, size: int) -> bytes`
  - `class SensorConsumerServer:`
    - `__init__(self, config: MockConfig) -> None`
    - `start(self) -> None`
    - `stop(self) -> None`
    - internal `_accept_and_read()`, `_read_from_producer(sock)`
  - Accepts one producer connection, reads exact records, optionally stores raw bytes and/or decoded records for tests.

- `src/kc_sensor_mock/cli.py`
  - Replace old `kc-sensor-mock`/`kc-sensor-client` assumptions.
  - Final commands should expose producer and consumer roles explicitly.
  - Suggested scripts:
    - `kc-sensor-producer = kc_sensor_mock.cli:run_producer_cli`
    - `kc-sensor-consumer = kc_sensor_mock.cli:run_consumer_cli`

- `src/kc_sensor_mock/__init__.py`
  - Export updated public runtime names if package exports runtime symbols.

### Tests to rewrite or add
- `tests/test_producer.py` **(new)**
  - Replaces transport behavior currently covered in `tests/test_server_client.py` for producer-side streaming.
- `tests/test_consumer.py` **(new)**
  - Covers sink behavior and exact-byte reading.
- `tests/test_cli.py`
  - Update parser defaults, help output, runtime wiring, and error handling for new producer/consumer commands.
- `tests/test_capture.py`
  - Shift assertions to producer-side capture and end-to-end producer->consumer parity.
- `tests/test_config.py`
  - Update config keys/override behavior.
- `tests/perf/test_stream_rate.py`
  - Update manual perf test to run producer against consumer listener.
- `tests/test_server_client.py`
  - Remove after replacement or keep temporarily as migration checkpoint only.

### Documentation files to update
- `README.md`
  - Rewrite run instructions, architecture description, CLI usage.
- `AGENTS.md`
  - Update architecture wording and milestone language so future work does not regress to wrong roles.
- `docs/superpowers/specs/2026-04-22-sensor-stream-mock-design.md`
  - Patch spec to reflect confirmed architecture: producer client connects outward to consumer server.

## Proposed Config/API Shape

### `MockConfig` changes
Replace bind-centric fields with explicit transport-role fields:
- `consumer_host: str`
- `consumer_port: int`
- `bind_host: str`
- `bind_port: int`
- `device_id: int`
- `measurement_type: int`
- `rate_hz: int`
- `mode: str`
- `ring_buffer_capacity: int`
- `initial_sequence_number: int`
- `gps_latitude: float`
- `gps_longitude: float`
- `gps_altitude_m: float`
- `capture_path: Path | None`

Usage rules:
- Producer CLI primarily uses `consumer_host`/`consumer_port`.
- Consumer CLI primarily uses `bind_host`/`bind_port`.
- Shared config file may contain both so one repo config can launch either side.

## Test Strategy

### Framework
- Keep `pytest`.
- Preserve current TDD discipline: tests first, fail first, minimal implementation, rerun targeted tests, then full suite.

### What to test
1. **Producer transport behavior**
   - Producer connects to configured consumer endpoint.
   - Producer streams exact encoded records after connect.
   - Producer reconnect loop behaves correctly after disconnect.
   - Producer continues generating into ring buffer while disconnected.
   - Producer drops oldest records on overflow and reports `dropped_records_total`.
2. **Consumer transport behavior**
   - Consumer accepts one producer connection.
   - Consumer reads exact 632-byte boundaries.
   - Consumer rejects partial record stream by surfacing connection error.
   - Consumer can decode and validate received records.
3. **Capture behavior**
   - Producer capture bytes exactly equal bytes delivered to consumer.
   - Capture rollback still happens on send failure.
4. **CLI wiring**
   - Producer CLI loads config, starts producer, handles shutdown cleanly.
   - Consumer CLI binds listener, handles shutdown cleanly.
   - Help output reflects new option names/defaults.
5. **Config behavior**
   - New host/port fields validate correctly.
   - Overrides map to correct runtime role.
6. **Manual perf lane**
   - Producer sends to consumer at target rate; perf test remains opt-in only.

### What not to test
- No OS-specific socket backlog tuning.
- No real network fault injection beyond controlled disconnect/failure cases.
- No multi-client or multi-producer scenarios.
- No handshake or negotiation behavior.

### Test file structure
- `tests/test_protocol.py` stays protocol-only.
- `tests/test_generator.py` and `tests/test_ring_buffer.py` remain isolated unit tests.
- New transport tests split by runtime role to avoid semantic confusion.

## Acceptance Criteria Per Unit

### Unit: protocol core
- Existing 632-byte record tests remain green unchanged.
- No binary contract changes.

### Unit: producer runtime
- Starts without binding a listening socket.
- Connects outward to configured consumer endpoint.
- Sends only encoded record bytes, no framing or control preamble.
- On disconnect, stops using dead socket and retries connection.
- While disconnected, keeps newest buffered data and drops oldest on overflow.

### Unit: consumer runtime
- Binds/listens on configured address.
- Accepts one producer at a time.
- Reads exact fixed-size records and can decode them.
- Stops cleanly on EOF, SIGINT, and SIGTERM when run from CLI.

### Unit: capture
- Captured file equals bytes actually transmitted by producer in controlled test.
- Failed send does not leave unsent bytes in capture file.

### Unit: config
- Producer and consumer each read only relevant endpoint fields.
- CLI overrides correctly replace config file values.
- Invalid port/rate/measurement values still fail fast.

### Unit: documentation
- README examples use producer/consumer terminology only.
- Spec and AGENTS docs describe outward producer connection, not old listener-sender model.

## Task Breakdown

### Task 1: Update spec and project docs before code changes

**Files:**
- Modify: `docs/superpowers/specs/2026-04-22-sensor-stream-mock-design.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

- [ ] **Step 1: Write failing documentation expectation notes in a scratch checklist**

Create checklist of phrases that must disappear:
- `single-client TCP server that streams records continuously`
- `reference client connects to mock`
- any wording where producer listens and consumer connects

- [ ] **Step 2: Update spec text to reversed role model**

Edit sections so they state:
- producer client connects outward to consumer server
- no handshake
- raw stream starts immediately after connect
- consumer server reads fixed records

- [ ] **Step 3: Update README architecture and run commands**

README must show:
- how to start consumer listener
- how to start producer client
- fixed record contract unchanged

- [ ] **Step 4: Update AGENTS.md workflow constraints**

Revise project overview, scope, milestones, and workflow rules to match producer-client architecture.

- [ ] **Step 5: Review docs for old server/client wording**

Search for transport-direction phrases and remove contradictions.

- [ ] **Step 6: Commit docs update**

```bash
git add docs/superpowers/specs/2026-04-22-sensor-stream-mock-design.md README.md AGENTS.md
git commit -m "docs: reverse transport architecture"
```

### Task 2: Refactor config model for explicit producer and consumer endpoints

**Files:**
- Modify: `src/kc_sensor_mock/config.py`
- Modify: `configs/default.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests for new endpoint fields**

Add tests for:
- loading `consumer_host` / `consumer_port`
- loading `bind_host` / `bind_port`
- producer CLI override path
- consumer CLI override path
- rejection of invalid port values for both endpoints

- [ ] **Step 2: Run targeted config tests to verify failure**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL because old config shape still uses `host` and `port` only.

- [ ] **Step 3: Update `MockConfig` and validation helpers**

Change dataclass fields and loader mapping to include both endpoint pairs while preserving existing validation quality.

- [ ] **Step 4: Update default config file**

Set sensible defaults, for example:
```toml
bind_host = "127.0.0.1"
bind_port = 9000
consumer_host = "127.0.0.1"
consumer_port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
```

- [ ] **Step 5: Run targeted config tests to verify pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit config refactor**

```bash
git add src/kc_sensor_mock/config.py configs/default.toml tests/test_config.py
git commit -m "refactor: split producer and consumer endpoints"
```

### Task 3: Introduce producer runtime and tests

**Files:**
- Create: `src/kc_sensor_mock/producer.py`
- Create: `tests/test_producer.py`
- Modify: `tests/test_capture.py`

- [ ] **Step 1: Write failing producer tests**

Add tests covering:
- producer connects outward to a listening test socket
- producer streams decodable records
- producer reconnects after consumer disconnect
- producer capture matches bytes received by consumer
- send failure rolls back capture bytes

- [ ] **Step 2: Run targeted producer tests to verify failure**

Run: `uv run pytest tests/test_producer.py tests/test_capture.py -v`
Expected: FAIL because `kc_sensor_mock.producer` does not exist.

- [ ] **Step 3: Implement `SensorProducerClient` minimally**

Core design:
- producer thread generates records into ring buffer
- sender thread attempts `socket.create_connection((consumer_host, consumer_port))`
- on connect, producer drains buffer via `sendall`
- on `OSError`, close socket and retry until stopped
- reuse capture rollback semantics from old server implementation

- [ ] **Step 4: Run targeted producer tests to verify pass**

Run: `uv run pytest tests/test_producer.py tests/test_capture.py -v`
Expected: PASS.

- [ ] **Step 5: Run regression tests for shared modules**

Run: `uv run pytest tests/test_protocol.py tests/test_generator.py tests/test_ring_buffer.py -v`
Expected: PASS.

- [ ] **Step 6: Commit producer runtime**

```bash
git add src/kc_sensor_mock/producer.py tests/test_producer.py tests/test_capture.py
git commit -m "feat: add outbound sensor producer"
```

### Task 4: Introduce consumer runtime and tests

**Files:**
- Create: `src/kc_sensor_mock/consumer.py`
- Create: `tests/test_consumer.py`
- Modify: `tests/test_producer.py`

- [ ] **Step 1: Write failing consumer tests**

Add tests covering:
- consumer binds/listens and accepts one producer
- consumer reads exact record sizes using `recv_exact`
- consumer can decode N records from live producer connection
- consumer surfaces partial-record disconnect as error in direct read helper

- [ ] **Step 2: Run targeted consumer tests to verify failure**

Run: `uv run pytest tests/test_consumer.py -v`
Expected: FAIL because `kc_sensor_mock.consumer` does not exist.

- [ ] **Step 3: Implement `SensorConsumerServer` minimally**

Core design:
- listener socket with `SO_REUSEADDR`
- one accept loop
- one active producer connection at a time
- helper for exact reads
- optional callback/storage path for tests to inspect decoded records

- [ ] **Step 4: Run targeted consumer tests to verify pass**

Run: `uv run pytest tests/test_consumer.py tests/test_producer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit consumer runtime**

```bash
git add src/kc_sensor_mock/consumer.py tests/test_consumer.py tests/test_producer.py
git commit -m "feat: add consumer listener"
```

### Task 5: Replace CLI with producer/consumer commands

**Files:**
- Modify: `src/kc_sensor_mock/cli.py`
- Modify: `src/kc_sensor_mock/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests for new commands**

Add tests for:
- `producer_parser()` defaults and help output
- `consumer_parser()` defaults and help output
- `run_producer_cli()` loads config and starts `SensorProducerClient`
- `run_consumer_cli()` loads config and starts `SensorConsumerServer`
- clean parser errors on bad config or connection issues

- [ ] **Step 2: Run targeted CLI tests to verify failure**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL because old parser/function names and scripts still exist.

- [ ] **Step 3: Implement new CLI parsers and runtime entry points**

Decision points:
- producer options override `consumer_host`, `consumer_port`
- consumer options override `bind_host`, `bind_port`
- keep shutdown watcher behavior for both roles
- print role-correct startup messages

- [ ] **Step 4: Update package scripts**

Change scripts to:
```toml
[project.scripts]
kc-sensor-producer = "kc_sensor_mock.cli:run_producer_cli"
kc-sensor-consumer = "kc_sensor_mock.cli:run_consumer_cli"
```

- [ ] **Step 5: Run targeted CLI tests to verify pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit CLI migration**

```bash
git add src/kc_sensor_mock/cli.py src/kc_sensor_mock/__init__.py pyproject.toml tests/test_cli.py
git commit -m "refactor: rename runtime roles in cli"
```

### Task 6: Remove old server/client transport path and migrate end-to-end tests

**Files:**
- Delete: `src/kc_sensor_mock/server.py`
- Delete: `src/kc_sensor_mock/client.py`
- Delete or replace: `tests/test_server_client.py`
- Modify: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing bootstrap/end-to-end tests for new script names**

Update tests so console-help checks target:
- `uv run kc-sensor-producer --help`
- `uv run kc-sensor-consumer --help`

Add or migrate end-to-end test asserting producer sends records to consumer listener.

- [ ] **Step 2: Run targeted end-to-end tests to verify failure**

Run: `uv run pytest tests/test_bootstrap.py tests/test_producer.py tests/test_consumer.py -v`
Expected: FAIL until old names/references are removed.

- [ ] **Step 3: Remove obsolete modules and old transport tests**

Delete old listener-sender implementation and direct receiver helper once all new imports are in place.

- [ ] **Step 4: Run migrated end-to-end tests to verify pass**

Run: `uv run pytest tests/test_bootstrap.py tests/test_producer.py tests/test_consumer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit transport cutover**

```bash
git add tests/test_bootstrap.py tests/test_producer.py tests/test_consumer.py
git rm src/kc_sensor_mock/server.py src/kc_sensor_mock/client.py tests/test_server_client.py
git commit -m "refactor: replace old transport roles"
```

### Task 7: Update manual perf lane and run full verification

**Files:**
- Modify: `tests/perf/test_stream_rate.py`
- Modify: `README.md` if perf command wording changed

- [ ] **Step 1: Write failing perf-lane test updates**

Adjust perf helper setup so it launches consumer listener first, then producer client, then measures received records and byte rate.

- [ ] **Step 2: Run perf test collection without opt-in to verify normal skip behavior remains**

Run: `uv run pytest tests/perf/test_stream_rate.py -v`
Expected: PASS or SKIPPED without `--run-perf` execution.

- [ ] **Step 3: Implement perf harness updates**

Keep manual lane isolated. Do not pull perf test into normal reliability gate.

- [ ] **Step 4: Run full automated suite**

Run: `uv run pytest tests -v`
Expected: PASS.

- [ ] **Step 5: Run manual perf lane**

Run: `uv run pytest tests/perf/test_stream_rate.py --run-perf -s -v`
Expected: PASS with throughput metrics printed.

- [ ] **Step 6: Commit perf and final verification updates**

```bash
git add tests/perf/test_stream_rate.py README.md
git commit -m "test: migrate perf lane to outbound producer"
```

## Documentation Scope

Must create or update:
- existing spec doc to correct transport direction
- implementation plan file created here
- README usage examples and architecture explanation
- AGENTS.md constraints/milestones
- CLI help text descriptions in code

No ADR required unless implementation reveals a second architecture pivot beyond confirmed direction reversal.

## Risk Points and Mitigations

1. **Risk: semantic confusion from old names**
   - **Mitigation:** introduce producer/consumer modules early; delete old modules before completion.
2. **Risk: reconnect logic causing flaky tests**
   - **Mitigation:** use deterministic local sockets and explicit timeouts in tests.
3. **Risk: capture semantics drift during transport refactor**
   - **Mitigation:** preserve rollback tests and exact-byte parity tests from start.
4. **Risk: config churn breaking both roles**
   - **Mitigation:** refactor config before runtime work and cover overrides thoroughly.

## Self-Review

### Spec coverage
- Connection direction reversal: covered by Tasks 1, 3, 4, 5, 6.
- No-handshake raw stream: covered by design decisions and producer/consumer acceptance criteria.
- Preserve binary format: covered by protocol acceptance criteria and regression tests.
- Keep perf lane isolated: covered by Task 7.

### Placeholder scan
- No `TODO`/`TBD` placeholders remain.
- Commands, files, and scope boundaries specified.

### Type consistency
- Runtime names consistently use `SensorProducerClient` and `SensorConsumerServer`.
- Config fields consistently use `consumer_*` and `bind_*` pairs.

Plan complete and saved to `docs/superpowers/plans/2026-04-23-reverse-stream-direction.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?