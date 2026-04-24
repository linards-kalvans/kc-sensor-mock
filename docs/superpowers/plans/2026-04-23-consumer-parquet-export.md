# Consumer Parquet Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional consumer-side parquet export with selectable volume/time batching that never blocks TCP receive progress.

**Architecture:** Keep decode on the consumer receive path, then hand decoded `SensorRecord` instances to a bounded export queue owned by the consumer. A dedicated parquet writer thread drains that queue, writes parquet files with `pyarrow`, rotates by the selected policy, logs export-side drops, and flushes remaining rows on clean shutdown.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `pyarrow`, standard library `threading`, `queue`/`collections`, `logging`, `argparse`, `tomllib`, existing protocol/config/consumer modules.

---

## Design Decisions

### 1. Keep decode on receive path
- **Why:** Fixed-record decode is likely cheap relative to parquet/file work. Immediate decode preserves stream validation and avoids a second decode path.
- **Decision:** `SensorConsumerServer` continues calling `decode_record(payload)` before any export handoff.

### 2. Add one bounded export queue between consumer and parquet writer
- **Why:** Parquet writes must never stall socket reads. A bounded queue creates explicit memory control.
- **Decision:** Queue decoded records; when full, drop oldest queued export record, increment a consumer-local counter, and log the drop.

### 3. Keep parquet implementation in a separate module
- **Why:** Consumer transport logic and parquet lifecycle logic are distinct responsibilities and easier to test independently when split.
- **Decision:** Add a dedicated `parquet_export.py` module with queueing, batching, rotation, flush, and failure tracking.

### 4. Support one active batching mode at a time
- **Why:** Spec explicitly rejected hybrid rotation in v1. A single active mode keeps config and tests simple.
- **Decision:** `volume` uses `parquet_max_records_per_file`; `time` uses `parquet_flush_interval_seconds`.

### 5. Treat parquet write failures as fatal when export is enabled
- **Why:** Silent export failure would make the system untrustworthy.
- **Decision:** Writer thread stores first fatal exception; consumer main loop/start-stop path surfaces it and terminates cleanly with explicit error.

## File-by-File Plan

### Create
- `src/kc_sensor_mock/parquet_export.py`
  - `@dataclass(frozen=True) class ParquetExportConfig`
  - `class ExportQueueOverflowWarningState`
  - `class ConsumerParquetExporter`
    - `start() -> None`
    - `stop() -> None`
    - `submit(record: SensorRecord) -> None`
    - `check_health() -> None`
    - internal `_writer_loop()`, `_flush_current_batch()`, `_rotate_file()`, `_next_output_path()`
- `tests/test_parquet_export.py`
  - Focused unit/integration tests for exporter behavior without TCP socket setup.

### Modify
- `src/kc_sensor_mock/config.py`
  - Extend `MockConfig` with parquet settings.
  - Add validators for enable flag, mode, output dir, queue capacity, volume threshold, time interval.
  - Extend `load_config()` override handling for new CLI/env keys.
- `src/kc_sensor_mock/consumer.py`
  - Inject optional exporter into `SensorConsumerServer`.
  - Start/stop exporter with consumer lifecycle.
  - Submit decoded records after successful decode.
  - Surface fatal exporter errors during receive loop and shutdown.
- `src/kc_sensor_mock/cli.py`
  - Add consumer CLI flags for parquet enablement and batching settings.
  - Extend `_consumer_overrides()`.
  - Ensure CLI error path reports invalid parquet config cleanly.
- `configs/default.toml`
  - Add disabled-by-default parquet settings with safe defaults.
- `tests/test_config.py`
  - Add config coverage for parquet fields and invalid combinations.
- `tests/test_cli.py`
  - Add CLI parser/override coverage for parquet flags.
- `tests/test_consumer.py`
  - Add integration tests proving receive path hands decoded records to exporter and flushes on stop.
- `README.md`
  - Document parquet export feature, flags, and config keys.
- `AGENTS.md`
  - Update workflow/architecture constraints if needed for consumer-side parquet export and new dependency.

### Do not modify unless necessary
- `src/kc_sensor_mock/protocol.py`
- `src/kc_sensor_mock/producer.py`
- `tests/test_protocol.py`
- `tests/test_producer.py`

## Public Interfaces

### `MockConfig`
Add fields:
- `parquet_enabled: bool`
- `parquet_output_dir: Path | None`
- `parquet_batch_mode: str | None`
- `parquet_max_records_per_file: int | None`
- `parquet_flush_interval_seconds: float | None`
- `parquet_queue_capacity: int | None`

Validation rules:
- If `parquet_enabled` is `False`, parquet-specific fields may be absent; defaults are accepted.
- If `parquet_enabled` is `True`, `parquet_output_dir` is required.
- If `parquet_enabled` is `True` and mode is omitted, set mode to `"volume"`.
- `parquet_batch_mode` must be one of `{"volume", "time"}`.
- `volume` mode requires positive `parquet_max_records_per_file`.
- `time` mode requires positive `parquet_flush_interval_seconds`.
- `parquet_queue_capacity` must be a positive integer when export is enabled.

### `ConsumerParquetExporter`
Suggested shape:

```python
@dataclass(frozen=True)
class ParquetExportConfig:
    output_dir: Path
    batch_mode: str
    max_records_per_file: int | None
    flush_interval_seconds: float | None
    queue_capacity: int


class ConsumerParquetExporter:
    def __init__(self, config: ParquetExportConfig, *, logger: logging.Logger | None = None) -> None: ...
    def start(self) -> None: ...
    def submit(self, record: SensorRecord) -> None: ...
    def check_health(self) -> None: ...
    def stop(self) -> None: ...
```

Behavior:
- `start()` creates output directory if needed and starts writer thread.
- `submit()` enqueues decoded record or drops oldest queued record before enqueueing newest one.
- `check_health()` raises stored fatal writer exception if one occurred.
- `stop()` signals writer, drains queue, flushes final batch, joins thread, then re-raises fatal exception if present.

### Consumer integration point
Inside `_read_from_producer()`:

```python
payload = recv_exact(producer_socket, RECORD_SIZE)
record = decode_record(payload)
if self._exporter is not None:
    self._exporter.check_health()
    self._exporter.submit(record)
```

After loop exit and during stop:
- call `self._exporter.stop()` if exporter exists.
- ensure fatal exporter exception is not swallowed.

## Test Strategy

### Framework
- Keep `pytest`.
- Follow TDD strictly: write failing tests first, run targeted test, implement minimum code, rerun targeted test, then broader suite.

### What to test
1. **Config validation**
   - parquet disabled defaults load.
   - parquet enabled requires output dir.
   - `volume` mode requires record threshold.
   - `time` mode requires flush interval.
   - CLI overrides map to correct config values.
2. **Exporter core**
   - disabled path not needed because exporter is never constructed.
   - volume mode writes parquet file after configured row count.
   - time mode writes parquet file after configured interval.
   - queue overflow drops oldest queued export record and logs cumulative count.
   - slow writer does not block `submit()` from accepting newest records after drop-oldest behavior.
   - stop flushes final partial batch.
   - file naming is unique and includes mode.
3. **Consumer integration**
   - consumer starts exporter when parquet enabled.
   - decoded records are submitted to exporter.
   - exporter stop happens during consumer stop.
   - fatal exporter error is surfaced rather than silently ignored.
4. **CLI/docs**
   - consumer parser exposes parquet flags.
   - help text includes defaults where relevant.
   - README examples reflect new config/CLI knobs.

### What NOT to test
- Compression ratio or write throughput benchmarks.
- Multi-writer export.
- Replay from parquet into TCP stream.
- Producer-side behavior unrelated to consumer export.

## Acceptance Criteria Per Unit

### Unit: config
- `load_config()` accepts parquet-disabled default config without changing current runtime behavior.
- Invalid enabled-mode combinations fail fast with clear error messages.
- CLI overrides for parquet fields replace config-file values correctly.

### Unit: exporter
- Writes parquet rows with all fixed record fields plus `values` list column.
- Rotates by configured `volume` or `time` policy.
- Drops oldest queued export record on overflow and logs count.
- Flushes final partial batch on stop.
- Raises explicit error on fatal write failure.

### Unit: consumer
- When parquet export is disabled, behavior remains unchanged.
- When enabled, decoded records are exported without blocking socket read path on file writes.
- Consumer stop drains and flushes exporter state.
- Fatal exporter error causes explicit failure, not silent degradation.

### Unit: CLI/docs
- Consumer CLI exposes parquet enablement, output dir, batching mode, threshold/interval, and queue capacity options.
- README/config examples show volume mode as default and time mode as optional.

## Task Breakdown

### Task 1: Add parquet config surface and defaults

**Files:**
- Modify: `src/kc_sensor_mock/config.py`
- Modify: `configs/default.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests for parquet-disabled defaults and enabled validation**

Add tests to `tests/test_config.py` for these exact cases:

```python
def test_load_config_defaults_parquet_to_disabled(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.parquet_enabled is False
    assert config.parquet_output_dir is None
    assert config.parquet_batch_mode is None


def test_load_config_requires_output_dir_when_parquet_enabled(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="parquet_output_dir"):
        load_config(_write_config(tmp_path, parquet_enabled="true"))
```
```

Also add failing tests for:
- `parquet_enabled = true` + `parquet_batch_mode = "volume"` without `parquet_max_records_per_file`
- `parquet_enabled = true` + `parquet_batch_mode = "time"` without `parquet_flush_interval_seconds`
- enabled export with valid volume settings loads successfully
- enabled export with valid time settings loads successfully

- [ ] **Step 2: Run targeted config tests to verify failure**

Run:
```bash
uv run pytest tests/test_config.py -v
```

Expected: failures mentioning missing `MockConfig` parquet fields or missing config validation.

- [ ] **Step 3: Extend `MockConfig` and validators**

Update `src/kc_sensor_mock/config.py` with new dataclass fields and helpers:

```python
VALID_PARQUET_BATCH_MODES = {"volume", "time"}


def _validate_optional_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")
    return value


def _validate_positive_float(name: str, value: object) -> float:
    if type(value) is bool or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    numeric = float(value)
    if numeric <= 0:
        raise ValueError(f"{name} must be positive")
    return numeric
```

Implement load rules exactly as listed in **Public Interfaces**.
Resolve `parquet_output_dir` relative to config file path, mirroring current capture-path behavior.

- [ ] **Step 4: Add disabled-by-default parquet settings to `configs/default.toml`**

Add keys:

```toml
parquet_enabled = false
parquet_output_dir = ""
parquet_batch_mode = ""
parquet_max_records_per_file = 1000
parquet_flush_interval_seconds = 1.0
parquet_queue_capacity = 4096
```

Use empty-string values for path/mode so disabled config stays explicit without forcing exporter startup.

- [ ] **Step 5: Run targeted config tests to verify pass**

Run:
```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS.

### Task 2: Add standalone parquet exporter module

**Files:**
- Create: `src/kc_sensor_mock/parquet_export.py`
- Test: `tests/test_parquet_export.py`

- [ ] **Step 1: Write failing exporter tests for volume flush and shutdown flush**

Create `tests/test_parquet_export.py` with tests shaped like:

```python
def test_volume_mode_writes_file_after_threshold(tmp_path: Path) -> None:
    exporter = ConsumerParquetExporter(
        ParquetExportConfig(
            output_dir=tmp_path,
            batch_mode="volume",
            max_records_per_file=2,
            flush_interval_seconds=None,
            queue_capacity=8,
        )
    )
    exporter.start()
    exporter.submit(_record(sequence_number=1))
    exporter.submit(_record(sequence_number=2))
    exporter.stop()
    assert list(tmp_path.glob("*.parquet"))
```
```

Also write failing tests for:
- time mode flush using short interval and polling wait
- stop flushes one-record partial batch
- overflow drops oldest queued record and logs count
- file contains `values` list column and correct `sequence_number` values after reading back with `pyarrow.parquet.read_table`

- [ ] **Step 2: Run targeted exporter tests to verify failure**

Run:
```bash
uv run pytest tests/test_parquet_export.py -v
```

Expected: FAIL because module/class does not exist.

- [ ] **Step 3: Add dependency using `uv`**

Run:
```bash
uv add pyarrow
```

Expected: `pyproject.toml` and lockfile update via `uv`, no manual edits.

- [ ] **Step 4: Implement minimal exporter**

Create `src/kc_sensor_mock/parquet_export.py` with:
- `ParquetExportConfig`
- queue storage using `collections.deque`
- `threading.Condition` for producer/writer coordination
- helper to convert `SensorRecord` to row dict
- `pyarrow.Table.from_pylist(...)`
- `pyarrow.parquet.write_table(...)`
- UTC timestamped file naming

Key internal state:

```python
self._pending: deque[SensorRecord]
self._pending_count: int
self._dropped_records_total: int
self._fatal_error: Exception | None
self._current_batch: list[SensorRecord]
self._file_index: int
self._stop_requested: bool
```

Implementation rules:
- `submit()` never waits for file writes.
- when queue full, `popleft()` oldest pending record before `append()` newest.
- writer loop wakes on new record, timeout, or stop request.
- volume mode flushes when current batch length reaches threshold.
- time mode flushes when oldest row in current batch has waited past interval.
- `stop()` drains queue into final batch and flushes once.

- [ ] **Step 5: Run exporter tests to verify pass**

Run:
```bash
uv run pytest tests/test_parquet_export.py -v
```

Expected: PASS.

### Task 3: Integrate exporter into consumer runtime

**Files:**
- Modify: `src/kc_sensor_mock/consumer.py`
- Test: `tests/test_consumer.py`
- Test: `tests/test_parquet_export.py`

- [ ] **Step 1: Write failing consumer integration tests**

Add tests to `tests/test_consumer.py` for:

```python
def test_consumer_submits_decoded_records_to_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list[int] = []

    class FakeExporter:
        def start(self) -> None: ...
        def check_health(self) -> None: ...
        def submit(self, record: SensorRecord) -> None:
            submitted.append(record.sequence_number)
        def stop(self) -> None: ...
```
```

Cover these exact behaviors:
- exporter is created and started when `config.parquet_enabled` is true
- decoded record is submitted after successful decode
- exporter stop is called during `consumer.stop()`
- if `check_health()` or `submit()` raises, consumer surfaces error instead of silently swallowing it

- [ ] **Step 2: Run targeted consumer tests to verify failure**

Run:
```bash
uv run pytest tests/test_consumer.py -v
```

Expected: FAIL because consumer has no exporter integration.

- [ ] **Step 3: Implement consumer integration**

Modify `src/kc_sensor_mock/consumer.py`:
- add `_exporter: ConsumerParquetExporter | None`
- build exporter config from `MockConfig` in `start()` when enabled
- start exporter before launching accept thread
- in `_read_from_producer()`, call `check_health()` and `submit(record)` after decode
- in `stop()`, stop exporter after stopping listener/thread, then re-raise fatal export error if present

Suggested helper:

```python
def _build_parquet_exporter(self) -> ConsumerParquetExporter | None:
    if not self._config.parquet_enabled:
        return None
    return ConsumerParquetExporter(
        ParquetExportConfig(
            output_dir=self._config.parquet_output_dir,
            batch_mode=self._config.parquet_batch_mode or "volume",
            max_records_per_file=self._config.parquet_max_records_per_file,
            flush_interval_seconds=self._config.parquet_flush_interval_seconds,
            queue_capacity=self._config.parquet_queue_capacity or 4096,
        )
    )
```

- [ ] **Step 4: Run targeted consumer/exporter tests**

Run:
```bash
uv run pytest tests/test_consumer.py tests/test_parquet_export.py -v
```

Expected: PASS.

### Task 4: Add consumer CLI/config overrides for parquet export

**Files:**
- Modify: `src/kc_sensor_mock/cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing CLI parser tests**

Add tests for these exact options:
- `--parquet-enabled`
- `--parquet-output-dir`
- `--parquet-batch-mode`
- `--parquet-max-records-per-file`
- `--parquet-flush-interval-seconds`
- `--parquet-queue-capacity`

Example test shape:

```python
def test_consumer_parser_has_parquet_options() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args([
        "--parquet-enabled",
        "--parquet-output-dir", "/tmp/out",
        "--parquet-batch-mode", "time",
        "--parquet-flush-interval-seconds", "2.5",
        "--parquet-queue-capacity", "32",
    ])
    assert args.parquet_enabled is True
    assert args.parquet_output_dir == "/tmp/out"
    assert args.parquet_batch_mode == "time"
```

- [ ] **Step 2: Run targeted CLI tests to verify failure**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: FAIL because parser lacks parquet options.

- [ ] **Step 3: Implement CLI flags and override mapping**

Modify `consumer_parser()` and `_consumer_overrides()`:

```python
parser.add_argument("--parquet-enabled", action="store_true", help="Enable consumer parquet export")
parser.add_argument("--parquet-output-dir", dest="parquet_output_dir", help="Parquet output directory override")
parser.add_argument("--parquet-batch-mode", choices=("volume", "time"), dest="parquet_batch_mode", help="Parquet batching mode override")
parser.add_argument("--parquet-max-records-per-file", type=int, dest="parquet_max_records_per_file", help="Volume-mode parquet row threshold override")
parser.add_argument("--parquet-flush-interval-seconds", type=float, dest="parquet_flush_interval_seconds", help="Time-mode parquet flush interval override")
parser.add_argument("--parquet-queue-capacity", type=int, dest="parquet_queue_capacity", help="Parquet export queue capacity override")
```

Map string path override to `Path`, same style as `capture_path`.
Only include `parquet_enabled=True` when flag present.

- [ ] **Step 4: Run targeted CLI/config tests**

Run:
```bash
uv run pytest tests/test_cli.py tests/test_config.py -v
```

Expected: PASS.

### Task 5: Add end-to-end parquet export coverage

**Files:**
- Modify: `tests/test_consumer.py`
- Modify: `tests/test_parquet_export.py`
- Modify: `src/kc_sensor_mock/consumer.py` (only if minimal fixes needed)

- [ ] **Step 1: Write failing end-to-end test for real consumer -> parquet file flow**

Add a socket-backed test that:
- starts `SensorConsumerServer` with parquet enabled, volume mode threshold `2`
- sends exactly two encoded records over a TCP connection
- stops consumer
- reads produced parquet file with `pyarrow.parquet.read_table`
- asserts row count `2`, expected `sequence_number` values, and `values` length `296`

- [ ] **Step 2: Run targeted end-to-end test to verify failure**

Run:
```bash
uv run pytest tests/test_consumer.py::test_consumer_writes_received_records_to_parquet -v
```

Expected: FAIL until integration and flush timing are correct.

- [ ] **Step 3: Fix minimal integration gaps**

If test reveals race/shutdown issues, adjust only these areas:
- writer wake-up signaling on stop
- exporter health checks after read loop exit
- final flush ordering in `consumer.stop()`

Do not redesign queue model.

- [ ] **Step 4: Run focused integration suite**

Run:
```bash
uv run pytest tests/test_consumer.py tests/test_parquet_export.py tests/test_cli.py tests/test_config.py -v
```

Expected: PASS.

### Task 6: Update docs and verify feature

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-04-23-consumer-parquet-export-design.md` (only if implementation reveals unavoidable naming/detail mismatch)

- [ ] **Step 1: Write docs changes**

Update `README.md` with:
- feature overview
- sample config block for volume mode
- sample CLI invocation for time mode
- note that export runs in dedicated writer thread and may drop oldest queued export records if writer falls behind

Update `AGENTS.md` with:
- parquet export now exists on consumer side
- `pyarrow` is required dependency
- export queue drop logs are expected behavior under sustained writer lag

- [ ] **Step 2: Run docs-adjacent verification commands**

Run:
```bash
uv run pytest tests/test_consumer.py tests/test_parquet_export.py tests/test_cli.py tests/test_config.py -v
uv run pytest -v
```

Expected: all reliability-lane tests PASS. Do not run `tests/perf/` here.

- [ ] **Step 3: Review git diff for scope control**

Confirm changed files are limited to planned config, consumer, exporter, tests, and docs. Reject unrelated refactors.

## Verification Commands

Run in this order before claiming completion:

```bash
uv run pytest tests/test_config.py tests/test_cli.py tests/test_parquet_export.py tests/test_consumer.py -v
uv run pytest -v
```

If `pyarrow` import or wheel issues appear, capture exact error and stop for user guidance rather than bypassing tests.

## Spec Coverage Check

- Optional consumer-side parquet export → Tasks 1-5
- CLI/config/env-controlled enablement → Tasks 1 and 4
- Non-blocking receive path via writer thread → Tasks 2, 3, 5
- Volume/time batching with volume default → Tasks 1, 2, 4
- `values` as array/list column → Task 2 and Task 5
- Drop-oldest queue overflow with logs → Tasks 2 and 5
- Graceful shutdown flush → Tasks 2, 3, 5
- Fatal write error semantics → Tasks 2 and 3
- Docs updates → Task 6

## Self-Review Notes

- No placeholder markers remain.
- Interface names are consistent across tasks: `ConsumerParquetExporter`, `ParquetExportConfig`, `parquet_*` config fields.
- Plan stays within confirmed scope and excludes raw archival mode, hybrid rotation, metrics endpoint, and producer changes.
