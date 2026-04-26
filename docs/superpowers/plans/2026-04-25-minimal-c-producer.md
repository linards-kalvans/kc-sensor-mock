# Minimal C Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal Linux-first C producer that replays full sensor records from CSV, serializes them into the existing 632-byte little-endian wire format, and streams them to the existing Python consumer without consumer changes.

**Architecture:** Keep the Python protocol contract as the single source of truth for record shape and expected bytes. Add a small standalone C program under `c/` with four focused units: record definition, CSV parsing, explicit little-endian serialization, and outbound TCP sending. Use pytest-driven integration tests plus tiny C test binaries to prove exact fixture parity and end-to-end consumer compatibility before adding any rate control or reconnect behavior.

**Tech Stack:** C99, POSIX sockets, standard C file I/O, `cc`/`gcc` on Linux, Python 3.12+, `pytest`, existing Python consumer/protocol modules, `uv` for Python command execution.

---

## 1. Design decisions

### 1.1 Keep Python protocol as contract source
- **Why:** Existing Python tests already lock `FORMAT == "<HHIIQQiii296H"` and `RECORD_SIZE == 632`. Reusing that contract avoids parallel schema drift.
- **Decision:** C code must mirror the existing field order and ranges exactly. No protocol changes, no new headers, no new framing.

### 1.2 Manual little-endian serialization instead of packed-struct writes
- **Why:** Packed structs are compiler-sensitive and less portable toward later embedded targets.
- **Decision:** `serialize.c` writes each field into a `uint8_t[632]` buffer with explicit helpers for `u16`, `u32`, `u64`, and `i32` little-endian encoding.

### 1.3 Full-record CSV replay for v1
- **Why:** User prioritized byte-for-byte verification over realism. Full-record CSV removes hidden generation logic from first milestone.
- **Decision:** One CSV row maps to one complete wire record: 9 metadata fields plus `value_0` through `value_295`.

### 1.4 Finite replay only
- **Why:** Minimal milestone is compatibility proof, not runtime parity.
- **Decision:** CLI supports `--emit-binary` and `--host/--port` send mode. Program sends all CSV rows in order, then exits. No reconnect, rate control, loop, or ring buffer.

### 1.5 Keep C implementation isolated from Python package runtime
- **Why:** This is a migration probe, not a Python extension module.
- **Decision:** Put C sources under `c/`, compile with a local `Makefile`, and invoke from pytest/instructions via subprocess.

## 2. File-by-file plan

### New files
- `c/Makefile`
  - Build `bin/c-producer` and one or more tiny test binaries under `c/build/`.
  - Expose targets: `all`, `clean`, `test-csv-parser`, `test-serializer`.
- `c/include/sensor_record.h`
  - Constants: `SENSOR_VALUES_COUNT`, `SENSOR_RECORD_SIZE`, measurement type enums.
  - `struct sensor_record` definition used only in memory.
- `c/include/csv_reader.h`
  - `int read_csv_records(const char *path, struct sensor_record **records_out, size_t *count_out, char *error_buf, size_t error_buf_size);`
  - `void free_csv_records(struct sensor_record *records);`
- `c/include/serialize.h`
  - `int serialize_record(const struct sensor_record *record, uint8_t out[SENSOR_RECORD_SIZE], char *error_buf, size_t error_buf_size);`
- `c/include/tcp_client.h`
  - `int send_records_to_endpoint(const char *host, uint16_t port, const struct sensor_record *records, size_t count, char *error_buf, size_t error_buf_size);`
- `c/src/csv_reader.c`
  - Header validation, integer parsing, fixed-column row parsing, range checks.
- `c/src/serialize.c`
  - LE encoding helpers and record serializer.
- `c/src/tcp_client.c`
  - POSIX `socket/connect/send` wrapper that writes each 632-byte payload fully or fails.
- `c/src/main.c`
  - CLI argument parsing, mode selection, operator-facing errors, program exit codes.
- `c/tests/test_csv_reader.c`
  - Tiny assert-based C test binary for parser happy path + failure cases.
- `c/tests/test_serialize.c`
  - Tiny assert-based C test binary for size/range/known-byte expectations.
- `tests/c_fixtures/minimal_record.csv`
  - Single-row canonical full-record CSV fixture.
- `tests/c_fixtures/minimal_record.bin`
  - Exact 632-byte expected binary fixture matching the CSV row.
- `tests/test_c_producer.py`
  - Pytest integration tests for build, emit-binary mode, and Python-consumer compatibility.

### Existing files to modify
- `README.md`
  - Add C producer build/run section and note exact scope boundaries.
- `AGENTS.md`
  - Add minimal C producer milestone/constraints so future work follows same contract.
- `docs/superpowers/specs/2026-04-25-minimal-c-producer-design.md`
  - Only if implementation planning uncovers a true mismatch. Otherwise leave unchanged.

### Files intentionally not modified
- `src/kc_sensor_mock/protocol.py`
- `src/kc_sensor_mock/consumer.py`
- `src/kc_sensor_mock/producer.py`
- `src/kc_sensor_mock/config.py`
- `src/kc_sensor_mock/cli.py`

Reason: accepted requirements say Python consumer must work unchanged; minimal C producer should not force Python runtime changes.

## 3. Test strategy

### Framework
- Use **pytest** as outer integration harness because repo already standardizes on it.
- Use **small C assert binaries** for low-level parser/serializer TDD where Python subprocess assertions would be too indirect.
- Run Python tests with `uv run pytest ...`.
- Build C code with `make -C c ...`.

### What to test
1. **CSV contract**
   - header must match exact 305-column schema
   - row must parse into expected fields
   - invalid measurement type fails
   - truncated row fails
   - out-of-range numeric value fails
2. **Serializer contract**
   - serialized record length is exactly 632 bytes
   - little-endian byte order matches Python golden fixture exactly
   - invalid value ranges fail before sending
3. **CLI/runtime behavior**
   - `--emit-binary` writes exact fixture bytes for canonical CSV
   - send mode connects outward to Python consumer and exits 0 on success
   - connect failure exits non-zero with useful stderr message
4. **End-to-end compatibility**
   - Python consumer receives records from C producer without code changes
   - Python `decode_record` of received payload matches CSV fixture values exactly

### What NOT to test
- rate accuracy
- reconnect loops
- ring buffer behavior
- capture file behavior
- multi-connection behavior
- embedded transport/HAL integration

### Test file structure
- `c/tests/test_csv_reader.c`: parser unit coverage
- `c/tests/test_serialize.c`: serializer unit coverage
- `tests/test_c_producer.py`: repo-level integration coverage
- `tests/c_fixtures/`: canonical CSV/bin fixtures shared by C and Python integration tests

## 4. Acceptance criteria per unit

### Unit: CSV reader
- Reads canonical CSV with exact expected schema.
- Produces one or more `struct sensor_record` values with exact integer field contents.
- Rejects malformed headers, missing values, extra columns, and out-of-range fields with explicit errors.

### Unit: serializer
- Emits exactly 632 bytes for every valid record.
- Byte stream for canonical fixture exactly matches `tests/c_fixtures/minimal_record.bin`.
- Rejects invalid `measurement_type`, invalid array length assumptions, and out-of-range field values.

### Unit: TCP sender
- Connects to supplied host/port as outbound client.
- Fully sends serialized payload for each record in order.
- Returns non-zero failure on connect or short-send error.

### Unit: CLI
- `bin/c-producer --csv <path> --emit-binary <out>` writes exact bytes and exits 0.
- `bin/c-producer --csv <path> --host 127.0.0.1 --port <port>` sends all rows and exits 0.
- Missing required options or invalid combinations print usage and exit non-zero.

### Unit: docs
- README documents how to build and verify the minimal C producer.
- AGENTS notes that v1 C producer is replay-first, Linux-first, and must preserve Python wire contract unchanged.

## 5. Documentation scope
- Update `README.md` with:
  - build command
  - emit-binary verification command
  - end-to-end command against Python consumer
  - explicit note that rate/reconnect are deferred
- Update `AGENTS.md` with:
  - minimal C producer now in scope
  - verification-first constraint
  - manual serialization requirement

## 6. Task breakdown

### Task 1: Add canonical C fixtures and failing integration test scaffold

**Files:**
- Create: `tests/c_fixtures/minimal_record.csv`
- Create: `tests/c_fixtures/minimal_record.bin`
- Create: `tests/test_c_producer.py`
- Modify: `README.md`

- [ ] **Step 1: Add canonical CSV fixture**

Create `tests/c_fixtures/minimal_record.csv` with one header row and one data row matching the Python golden-byte test values. Use:

```csv
device_id,measurement_type,sequence_number,dropped_records_total,sensor_timestamp_us,gps_timestamp_us,gps_latitude_e7,gps_longitude_e7,gps_altitude_mm,value_0,value_1,value_2,value_3,value_4,...,value_295
4660,2,16909060,84281096,72623859790382856,1230066625199609624,-123456789,168496141,-1000,258,772,1541,2055,0,...,0
```

For columns `value_4` through `value_295`, write `0`.

- [ ] **Step 2: Add canonical binary fixture generator note and checked-in fixture**

Create `tests/c_fixtures/minimal_record.bin` whose first bytes are:

```text
34 12 02 00 04 03 02 01 08 07 06 05 08 07 06 05
04 03 02 01 18 17 16 15 14 13 12 11 eb 32 a4 f8
0d 0c 0b 0a 18 fc ff ff 02 01 04 03 05 06 07 08
```

and whose total length is exactly 632 bytes, with all remaining `values` bytes zero-filled.

- [ ] **Step 3: Write failing pytest for emit-binary mode**

Create `tests/test_c_producer.py` with initial test skeleton:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C_DIR = ROOT / "c"
FIXTURES = Path(__file__).resolve().parent / "c_fixtures"


def test_emit_binary_matches_golden_fixture(tmp_path: Path) -> None:
    output_path = tmp_path / "record.bin"
    result = subprocess.run(
        [str(C_DIR / "bin" / "c-producer"), "--csv", str(FIXTURES / "minimal_record.csv"), "--emit-binary", str(output_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert output_path.read_bytes() == (FIXTURES / "minimal_record.bin").read_bytes()
```

- [ ] **Step 4: Run failing pytest to confirm missing binary/build path**

Run:

```bash
uv run pytest tests/test_c_producer.py::test_emit_binary_matches_golden_fixture -v
```

Expected: **FAIL** with missing `c/bin/c-producer` or similar file-not-found failure.

### Task 2: Add C project skeleton and serializer-first TDD

**Files:**
- Create: `c/Makefile`
- Create: `c/include/sensor_record.h`
- Create: `c/include/serialize.h`
- Create: `c/src/serialize.c`
- Create: `c/tests/test_serialize.c`
- Test: `tests/test_c_producer.py`

- [ ] **Step 1: Write failing C serializer unit test**

Create `c/tests/test_serialize.c`:

```c
#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "sensor_record.h"
#include "serialize.h"

int main(void) {
    struct sensor_record record = {0};
    uint8_t out[SENSOR_RECORD_SIZE] = {0};

    record.device_id = 0x1234;
    record.measurement_type = MEASUREMENT_TYPE_BACKGROUND_SPECTRA;
    record.sequence_number = 0x01020304;
    record.dropped_records_total = 0x05060708;
    record.sensor_timestamp_us = 0x0102030405060708ULL;
    record.gps_timestamp_us = 0x1112131415161718ULL;
    record.gps_latitude_e7 = -123456789;
    record.gps_longitude_e7 = 0x0A0B0C0D;
    record.gps_altitude_mm = -1000;
    record.values[0] = 0x0102;
    record.values[1] = 0x0304;
    record.values[2] = 0x0605;
    record.values[3] = 0x0807;

    assert(serialize_record(&record, out, NULL, 0) == 0);
    assert(out[0] == 0x34);
    assert(out[1] == 0x12);
    assert(out[2] == 0x02);
    assert(out[3] == 0x00);
    assert(out[40] == 0x02);
    assert(out[41] == 0x01);
    assert(out[46] == 0x07);
    assert(out[47] == 0x08);
    return 0;
}
```

- [ ] **Step 2: Add Makefile target and compile failing test**

Create minimal `c/Makefile` target:

```make
CC ?= cc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -Iinclude
BUILD_DIR := build
BIN_DIR := bin

$(BUILD_DIR) $(BIN_DIR):
	mkdir -p $@

test-serializer: | $(BUILD_DIR)
	$(CC) $(CFLAGS) tests/test_serialize.c src/serialize.c -o $(BUILD_DIR)/test_serialize
	$(BUILD_DIR)/test_serialize
```

Run:

```bash
make -C c test-serializer
```

Expected: **FAIL** because headers and implementation do not exist yet.

- [ ] **Step 3: Add minimal record header and serializer API**

Create `c/include/sensor_record.h` with:

```c
#ifndef SENSOR_RECORD_H
#define SENSOR_RECORD_H

#include <stdint.h>

#define SENSOR_VALUES_COUNT 296
#define SENSOR_RECORD_SIZE 632
#define MEASUREMENT_TYPE_SPECTRA 1
#define MEASUREMENT_TYPE_BACKGROUND_SPECTRA 2

struct sensor_record {
    uint16_t device_id;
    uint16_t measurement_type;
    uint32_t sequence_number;
    uint32_t dropped_records_total;
    uint64_t sensor_timestamp_us;
    uint64_t gps_timestamp_us;
    int32_t gps_latitude_e7;
    int32_t gps_longitude_e7;
    int32_t gps_altitude_mm;
    uint16_t values[SENSOR_VALUES_COUNT];
};

#endif
```

Create `c/include/serialize.h` with:

```c
#ifndef SERIALIZE_H
#define SERIALIZE_H

#include <stddef.h>
#include <stdint.h>

#include "sensor_record.h"

int serialize_record(const struct sensor_record *record, uint8_t out[SENSOR_RECORD_SIZE], char *error_buf, size_t error_buf_size);

#endif
```

- [ ] **Step 4: Implement minimal serializer**

Create `c/src/serialize.c` with explicit LE writes for all fields. Include helper signatures:

```c
static void write_u16_le(uint8_t *out, uint16_t value);
static void write_u32_le(uint8_t *out, uint32_t value);
static void write_u64_le(uint8_t *out, uint64_t value);
static void write_i32_le(uint8_t *out, int32_t value);
```

`serialize_record(...)` should:
- reject null pointers
- validate `measurement_type` is `1` or `2`
- write metadata bytes at offsets `0..39`
- write 296 `uint16_t` values starting at byte offset `40`
- return `0` on success, `1` on validation failure

- [ ] **Step 5: Run serializer unit test and pytest again**

Run:

```bash
make -C c test-serializer
uv run pytest tests/test_c_producer.py::test_emit_binary_matches_golden_fixture -v
```

Expected:
- serializer C unit test: **PASS**
- pytest: still **FAIL** because CLI binary does not exist yet

### Task 3: Add CSV parser with strict schema validation

**Files:**
- Create: `c/include/csv_reader.h`
- Create: `c/src/csv_reader.c`
- Create: `c/tests/test_csv_reader.c`
- Test: `tests/test_c_producer.py`

- [ ] **Step 1: Write failing parser unit test**

Create `c/tests/test_csv_reader.c`:

```c
#include <assert.h>
#include <stddef.h>

#include "csv_reader.h"

int main(void) {
    struct sensor_record *records = NULL;
    size_t count = 0;
    char error_buf[256] = {0};

    assert(read_csv_records("../tests/c_fixtures/minimal_record.csv", &records, &count, error_buf, sizeof(error_buf)) == 0);
    assert(count == 1);
    assert(records[0].device_id == 4660);
    assert(records[0].measurement_type == 2);
    assert(records[0].values[0] == 258);
    assert(records[0].values[3] == 2055);
    free_csv_records(records);
    return 0;
}
```

- [ ] **Step 2: Add failing Makefile parser target**

Extend `c/Makefile`:

```make
test-csv-parser: | $(BUILD_DIR)
	$(CC) $(CFLAGS) tests/test_csv_reader.c src/csv_reader.c src/serialize.c -o $(BUILD_DIR)/test_csv_reader
	cd $(BUILD_DIR) && ./test_csv_reader
```

Run:

```bash
make -C c test-csv-parser
```

Expected: **FAIL** because parser API/implementation do not exist yet.

- [ ] **Step 3: Add parser header**

Create `c/include/csv_reader.h`:

```c
#ifndef CSV_READER_H
#define CSV_READER_H

#include <stddef.h>

#include "sensor_record.h"

int read_csv_records(const char *path, struct sensor_record **records_out, size_t *count_out, char *error_buf, size_t error_buf_size);
void free_csv_records(struct sensor_record *records);

#endif
```

- [ ] **Step 4: Implement strict CSV parser**

`c/src/csv_reader.c` should:
- open file with `fopen`
- read line-by-line with `getline`
- validate exact header string against generated expected header
- split each data line on commas
- require exactly 305 columns
- parse every field with `strtoull` / `strtoll`
- range-check values for uint16/uint32/uint64/int32 fields
- dynamically grow record array with `realloc`
- return explicit error text on first failure

Do **not** support quoted commas, optional whitespace normalization, or schema aliases.

- [ ] **Step 5: Run parser unit test**

Run:

```bash
make -C c test-csv-parser
```

Expected: **PASS**.

### Task 4: Add CLI binary and emit-binary mode

**Files:**
- Create: `c/src/main.c`
- Modify: `c/Makefile`
- Test: `tests/test_c_producer.py`

- [ ] **Step 1: Expand pytest with CLI usage test**

Add to `tests/test_c_producer.py`:

```python
def test_missing_mode_arguments_fail_with_usage() -> None:
    result = subprocess.run(
        [str(C_DIR / "bin" / "c-producer"), "--csv", str(FIXTURES / "minimal_record.csv")],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--emit-binary" in result.stderr or "--host" in result.stderr
```

- [ ] **Step 2: Write minimal CLI implementation**

Create `c/src/main.c` that supports exactly two valid forms:

```text
c-producer --csv <path> --emit-binary <out>
c-producer --csv <path> --host <host> --port <port>
```

Implementation requirements:
- parse argv manually
- reject missing `--csv`
- reject mixing `--emit-binary` with `--host/--port`
- call `read_csv_records`
- in emit mode, serialize all records and append them to output file
- print errors to `stderr`
- return `0` on success, `1` on usage/config/runtime error

- [ ] **Step 3: Add final build target**

Extend `c/Makefile`:

```make
all: $(BIN_DIR)/c-producer

$(BIN_DIR)/c-producer: | $(BUILD_DIR) $(BIN_DIR)
	$(CC) $(CFLAGS) src/main.c src/csv_reader.c src/serialize.c src/tcp_client.c -o $(BIN_DIR)/c-producer
```

Temporarily add stub `src/tcp_client.c` if needed to satisfy linker before send mode is implemented.

- [ ] **Step 4: Run targeted pytest for emit mode**

Run:

```bash
make -C c all
uv run pytest tests/test_c_producer.py::test_emit_binary_matches_golden_fixture tests/test_c_producer.py::test_missing_mode_arguments_fail_with_usage -v
```

Expected: both tests **PASS**.

### Task 5: Add TCP send mode and Python consumer integration test

**Files:**
- Create: `c/include/tcp_client.h`
- Create: `c/src/tcp_client.c`
- Modify: `tests/test_c_producer.py`

**Files:**
- Create: `c/include/tcp_client.h`
- Create: `c/src/tcp_client.c`
- Modify: `tests/test_c_producer.py`

- [ ] **Step 1: Add failing integration test against Python consumer**

Extend `tests/test_c_producer.py` with:

```python
import socket
import threading

from kc_sensor_mock.consumer import recv_exact
from kc_sensor_mock.protocol import RECORD_SIZE, decode_record


def test_c_producer_streams_record_python_consumer_accepts(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()[:2]
    received = {}

    def accept_once() -> None:
        conn, _ = listener.accept()
        with conn:
            payload = recv_exact(conn, RECORD_SIZE)
        received["payload"] = payload

    thread = threading.Thread(target=accept_once)
    thread.start()
    result = subprocess.run(
        [
            str(C_DIR / "bin" / "c-producer"),
            "--csv", str(FIXTURES / "minimal_record.csv"),
            "--host", host,
            "--port", str(port),
        ],
        capture_output=True,
        text=True,
    )
    thread.join(timeout=2)
    listener.close()

    assert result.returncode == 0
    record = decode_record(received["payload"])
    assert record.device_id == 0x1234
    assert record.measurement_type == 2
    assert record.values[:4] == (0x0102, 0x0304, 0x0605, 0x0807)
```

- [ ] **Step 2: Run failing test**

Run:

```bash
make -C c all
uv run pytest tests/test_c_producer.py::test_c_producer_streams_record_python_consumer_accepts -v
```

Expected: **FAIL** because send mode is not implemented.

- [ ] **Step 3: Implement TCP client**

Create `c/include/tcp_client.h` and `c/src/tcp_client.c`.

Implementation details:
- use `getaddrinfo`
- iterate candidates until `connect` succeeds
- serialize each record into a local `uint8_t[632]`
- send in loop until all bytes for each record are written
- close socket on success/failure
- report connect/send errors via error buffer

- [ ] **Step 4: Wire send mode into CLI**

Update `main.c` to call `send_records_to_endpoint(...)` when `--host` and `--port` are supplied.

- [ ] **Step 5: Run targeted tests and full new test file**

Run:

```bash
make -C c clean all test-serializer test-csv-parser
uv run pytest tests/test_c_producer.py -v
```

Expected: all tests in `tests/test_c_producer.py` **PASS** and C unit targets **PASS**.

### Task 6: Update docs and verify no Python regressions

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update README**

Add section with exact commands:

```bash
make -C c all
./c/bin/c-producer --csv tests/c_fixtures/minimal_record.csv --emit-binary /tmp/minimal_record.bin
python - <<'PY'
from pathlib import Path
print(Path('/tmp/minimal_record.bin').read_bytes() == Path('tests/c_fixtures/minimal_record.bin').read_bytes())
PY
uv run kc-sensor-consumer --bind-host 127.0.0.1 --bind-port 9000
./c/bin/c-producer --csv tests/c_fixtures/minimal_record.csv --host 127.0.0.1 --port 9000
```

Document deferred features explicitly: no rate control, no reconnect, no ring buffer.

- [ ] **Step 2: Update AGENTS.md**

Add concise note that repo now contains a minimal standalone C producer under `c/` for protocol verification and that manual little-endian serialization is required for future C work.

- [ ] **Step 3: Run verification commands**

Run:

```bash
make -C c clean all test-serializer test-csv-parser
uv run pytest tests/test_c_producer.py tests/test_protocol.py tests/test_consumer.py -v
```

Expected:
- C targets: **PASS**
- Python protocol/consumer regression tests: **PASS**
- new C integration tests: **PASS**

## 7. Self-review

### Spec coverage check
- full-record CSV input: covered by Task 1 + Task 3
- exact 632-byte little-endian serialization: covered by Task 2
- binary fixture parity: covered by Task 1 + Task 4
- outbound stream to Python consumer: covered by Task 5
- Linux-first, extension-ready structure: covered by file layout and deferred options in Tasks 2–5
- docs updates: covered by Task 6

### Placeholder scan
- No `TODO` / `TBD` placeholders left.
- Each task names exact files and verification commands.
- Deferred features explicitly marked out of scope rather than deferred ambiguously.

### Type/interface consistency
- Shared API names are consistent across tasks: `read_csv_records`, `free_csv_records`, `serialize_record`, `send_records_to_endpoint`.
- Record shape and fixture values match existing Python protocol tests.
