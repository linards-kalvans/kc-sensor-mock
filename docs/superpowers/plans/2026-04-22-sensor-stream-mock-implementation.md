# Sensor Stream Mock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python v1 STM-style sensor mock that streams fixed-size little-endian binary sensor records over TCP.

**Architecture:** The project is a small Python package with focused modules for binary protocol packing, sample generation, buffering, configuration, TCP streaming, reference-client validation, and optional capture. The protocol contract is the central boundary: every generated, captured, and transmitted record is the same 632-byte `<HHIIQQiii296H` binary format.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, standard library `struct`, `socket`, `threading`, `argparse`, `tomllib`, and `tomli-w` only if config writing becomes necessary.

---

## File Structure

- Create: `pyproject.toml` via `uv init --package --name kc-sensor-mock`.
- Create: `src/kc_sensor_mock/__init__.py` for package version export.
- Create: `src/kc_sensor_mock/protocol.py` for `SensorRecord`, constants, struct packing/unpacking, scaled GPS helpers, and golden bytes support.
- Create: `src/kc_sensor_mock/sample_data.py` for the provided 296-value spectra sample and sample validation.
- Create: `src/kc_sensor_mock/ring_buffer.py` for a drop-oldest fixed-capacity record buffer.
- Create: `src/kc_sensor_mock/config.py` for TOML config loading and CLI override merging.
- Create: `src/kc_sensor_mock/generator.py` for rate-controlled and burst record generation.
- Create: `src/kc_sensor_mock/server.py` for single-client TCP streaming and optional capture.
- Create: `src/kc_sensor_mock/client.py` for the reference client read/unpack/validate flow.
- Create: `src/kc_sensor_mock/cli.py` for `kc-sensor-mock` and `kc-sensor-client` entry points.
- Create: `configs/default.toml` for default mock settings.
- Create: `tests/test_protocol.py`.
- Create: `tests/test_sample_data.py`.
- Create: `tests/test_ring_buffer.py`.
- Create: `tests/test_config.py`.
- Create: `tests/test_generator.py`.
- Create: `tests/test_server_client.py`.
- Create: `tests/test_capture.py`.
- Create: `tests/perf/test_stream_rate.py` for manual high-rate validation.

## Task 1: Initialize Python Project

**Files:**
- Create: `pyproject.toml`
- Create: `src/kc_sensor_mock/__init__.py`

- [ ] **Step 1: Initialize package with uv**

Run:

```bash
uv init --package --name kc-sensor-mock
```

Expected: creates `pyproject.toml`, `src/kc_sensor_mock/__init__.py`, and package metadata.

- [ ] **Step 2: Add pytest as a development dependency**

Run:

```bash
uv add --dev pytest
```

Expected: `pytest` is added to the dev dependency group and `uv.lock` is created.

- [ ] **Step 3: Configure CLI scripts**

Modify `pyproject.toml` so it contains:

```toml
[project.scripts]
kc-sensor-mock = "kc_sensor_mock.cli:run_server_cli"
kc-sensor-client = "kc_sensor_mock.cli:run_client_cli"
```

- [ ] **Step 4: Run the empty test suite**

Run:

```bash
uv run pytest
```

Expected: pytest runs successfully with either no tests collected or only generated template tests passing.

- [ ] **Step 5: Commit**

Run:

```bash
git add pyproject.toml uv.lock src/kc_sensor_mock
git commit -m "chore: initialize python package"
```

Expected: commit succeeds if the project is a git repository. If not, record that commit was skipped because the repository is not initialized.

## Task 2: Implement Binary Protocol

**Files:**
- Create: `tests/test_protocol.py`
- Create: `src/kc_sensor_mock/protocol.py`

- [ ] **Step 1: Write failing protocol tests**

Create `tests/test_protocol.py`:

```python
import struct

import pytest

from kc_sensor_mock.protocol import (
    FORMAT,
    MEASUREMENT_TYPE_BACKGROUND_SPECTRA,
    MEASUREMENT_TYPE_SPECTRA,
    RECORD_SIZE,
    SENSOR_VALUES_COUNT,
    SensorRecord,
    decode_record,
    encode_record,
    scale_altitude_mm,
    scale_latitude_e7,
    scale_longitude_e7,
)


def make_record() -> SensorRecord:
    return SensorRecord(
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        sequence_number=7,
        dropped_records_total=2,
        sensor_timestamp_us=1_778_000_000_000_001,
        gps_timestamp_us=1_778_000_000_000_002,
        gps_latitude_e7=566_718_316,
        gps_longitude_e7=242_391_946,
        gps_altitude_mm=35_000,
        values=tuple(range(SENSOR_VALUES_COUNT)),
    )


def test_record_size_is_632_bytes():
    assert FORMAT == "<HHIIQQiii296H"
    assert SENSOR_VALUES_COUNT == 296
    assert RECORD_SIZE == 632
    assert struct.calcsize(FORMAT) == RECORD_SIZE


def test_pack_unpack_roundtrip_preserves_fields():
    record = make_record()

    packed = encode_record(record)
    unpacked = decode_record(packed)

    assert len(packed) == RECORD_SIZE
    assert unpacked == record


def test_rejects_invalid_measurement_type():
    record = make_record()
    invalid = record.replace(measurement_type=99)

    with pytest.raises(ValueError, match="measurement_type"):
        encode_record(invalid)


def test_rejects_wrong_values_count():
    record = make_record().replace(values=(1, 2, 3))

    with pytest.raises(ValueError, match="296"):
        encode_record(record)


def test_rejects_out_of_range_uint16_value():
    record = make_record().replace(values=tuple([0] * 295 + [65_536]))

    with pytest.raises(ValueError, match="uint16"):
        encode_record(record)


def test_rejects_partial_record_decode():
    with pytest.raises(ValueError, match="632"):
        decode_record(b"\x00" * 631)


def test_scaling_helpers_are_deterministic():
    assert scale_latitude_e7(56.6718316) == 566_718_316
    assert scale_longitude_e7(24.2391946) == 242_391_946
    assert scale_altitude_mm(35.0) == 35_000


def test_background_measurement_type_is_supported():
    record = make_record().replace(measurement_type=MEASUREMENT_TYPE_BACKGROUND_SPECTRA)

    assert decode_record(encode_record(record)).measurement_type == 2
```

- [ ] **Step 2: Run protocol tests to verify failure**

Run:

```bash
uv run pytest tests/test_protocol.py -v
```

Expected: FAIL because `kc_sensor_mock.protocol` does not exist.

- [ ] **Step 3: Implement protocol module**

Create `src/kc_sensor_mock/protocol.py`:

```python
from __future__ import annotations

import struct
from dataclasses import dataclass, replace

SENSOR_VALUES_COUNT = 296
MEASUREMENT_TYPE_SPECTRA = 1
MEASUREMENT_TYPE_BACKGROUND_SPECTRA = 2
VALID_MEASUREMENT_TYPES = {
    MEASUREMENT_TYPE_SPECTRA,
    MEASUREMENT_TYPE_BACKGROUND_SPECTRA,
}

FORMAT = "<HHIIQQiii296H"
RECORD_SIZE = struct.calcsize(FORMAT)


@dataclass(frozen=True)
class SensorRecord:
    device_id: int
    measurement_type: int
    sequence_number: int
    dropped_records_total: int
    sensor_timestamp_us: int
    gps_timestamp_us: int
    gps_latitude_e7: int
    gps_longitude_e7: int
    gps_altitude_mm: int
    values: tuple[int, ...]

    def replace(self, **changes: object) -> SensorRecord:
        return replace(self, **changes)


def scale_latitude_e7(value: float) -> int:
    return round(value * 10_000_000)


def scale_longitude_e7(value: float) -> int:
    return round(value * 10_000_000)


def scale_altitude_mm(value: float) -> int:
    return round(value * 1_000)


def validate_record(record: SensorRecord) -> None:
    if record.measurement_type not in VALID_MEASUREMENT_TYPES:
        raise ValueError(f"measurement_type must be one of {sorted(VALID_MEASUREMENT_TYPES)}")
    if len(record.values) != SENSOR_VALUES_COUNT:
        raise ValueError(f"values must contain exactly {SENSOR_VALUES_COUNT} items")
    for value in record.values:
        if not 0 <= value <= 65_535:
            raise ValueError("values must contain uint16 items")


def encode_record(record: SensorRecord) -> bytes:
    validate_record(record)
    return struct.pack(
        FORMAT,
        record.device_id,
        record.measurement_type,
        record.sequence_number,
        record.dropped_records_total,
        record.sensor_timestamp_us,
        record.gps_timestamp_us,
        record.gps_latitude_e7,
        record.gps_longitude_e7,
        record.gps_altitude_mm,
        *record.values,
    )


def decode_record(payload: bytes) -> SensorRecord:
    if len(payload) != RECORD_SIZE:
        raise ValueError(f"record payload must be exactly {RECORD_SIZE} bytes")
    fields = struct.unpack(FORMAT, payload)
    record = SensorRecord(
        device_id=fields[0],
        measurement_type=fields[1],
        sequence_number=fields[2],
        dropped_records_total=fields[3],
        sensor_timestamp_us=fields[4],
        gps_timestamp_us=fields[5],
        gps_latitude_e7=fields[6],
        gps_longitude_e7=fields[7],
        gps_altitude_mm=fields[8],
        values=tuple(fields[9:]),
    )
    validate_record(record)
    return record
```

- [ ] **Step 4: Run protocol tests to verify pass**

Run:

```bash
uv run pytest tests/test_protocol.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/kc_sensor_mock/protocol.py tests/test_protocol.py
git commit -m "feat: define fixed sensor record protocol"
```

## Task 3: Add Sample Data Validation

**Files:**
- Create: `tests/test_sample_data.py`
- Create: `src/kc_sensor_mock/sample_data.py`

- [ ] **Step 1: Write failing sample data tests**

Create `tests/test_sample_data.py`:

```python
import pytest

from kc_sensor_mock.protocol import SENSOR_VALUES_COUNT
from kc_sensor_mock.sample_data import SAMPLE_VALUES, validate_values


def test_sample_values_have_required_count():
    assert len(SAMPLE_VALUES) == SENSOR_VALUES_COUNT


def test_sample_values_are_uint16():
    validate_values(SAMPLE_VALUES)


def test_validate_values_rejects_wrong_length():
    with pytest.raises(ValueError, match="296"):
        validate_values([1, 2, 3])


def test_validate_values_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="uint16"):
        validate_values([0] * 295 + [65_536])
```

- [ ] **Step 2: Run sample data tests to verify failure**

Run:

```bash
uv run pytest tests/test_sample_data.py -v
```

Expected: FAIL because `kc_sensor_mock.sample_data` does not exist.

- [ ] **Step 3: Implement sample data module**

Create `src/kc_sensor_mock/sample_data.py`:

```python
from __future__ import annotations

from kc_sensor_mock.protocol import SENSOR_VALUES_COUNT

SAMPLE_VALUES = (
    8970, 9093, 9216, 9220, 9128, 9285, 9024, 9216, 8806, 9053,
    8971, 9343, 9314, 9908, 9647, 10134, 9770, 10151, 9850, 10101,
    9736, 10102, 10030, 10514, 10254, 10549, 10919, 11145, 11620,
    11545, 11724, 11486, 11689, 11264, 11541, 11122, 11607, 11274,
    11776, 11887, 12997, 13706, 15024, 15614, 16638, 17034, 17985,
    18274, 19063, 18842, 19383, 18618, 18809, 18271, 18829, 18944,
    19583, 19456, 20048, 20200, 20755, 20818, 21768, 21506, 22443,
    22447, 23334, 23469, 24286, 24698, 25530, 26393, 27381, 27738,
    28038, 28160, 28262, 28781, 29380, 29944, 29743, 29696, 29696,
    29696, 29266, 28866, 28242, 28160, 27963, 28301, 28902, 29700,
    30429, 30966, 31349, 32863, 32934, 33129, 33389, 33482, 33834,
    33946, 33665, 33792, 33634, 33867, 33316, 33340, 32808, 32336,
    31645, 31856, 31792, 31534, 32158, 31937, 32040, 31744, 31573,
    31232, 30874, 31064, 30848, 31232, 31153, 31257, 31273, 31102,
    31262, 30982, 31460, 31058, 31517, 30918, 31442, 30957, 30607,
    30130, 30146, 30208, 29739, 30294, 29802, 29892, 29292, 29378,
    28562, 28501, 27825, 27649, 26766, 26794, 26277, 26154, 26407,
    25930, 25981, 25402, 25253, 24874, 24925, 24219, 24592, 23952,
    23832, 23440, 23176, 23317, 23290, 24144, 24999, 25910, 26278,
    27253, 27406, 28305, 28160, 29030, 29284, 29696, 29522, 29349,
    27960, 27570, 26896, 26996, 26519, 26696, 27029, 27411, 27648,
    27992, 28514, 28714, 29696, 29696, 29708, 29466, 29522, 29196,
    29317, 28296, 28582, 28010, 27421, 25519, 23638, 21569, 20245,
    19322, 19706, 20524, 22052, 23952, 24499, 25384, 24882, 25088,
    24576, 24677, 24402, 24487, 23970, 23665, 23106, 23236, 22935,
    22669, 22351, 22100, 21736, 21855, 21291, 21549, 20814, 20836,
    20480, 20277, 19810, 19492, 19086, 18597, 18134, 17622, 17408,
    17144, 16896, 16639, 16780, 16584, 16783, 16328, 16650, 16317,
    16639, 16296, 16477, 16141, 16536, 15912, 16505, 16053, 16416,
    15881, 16222, 15890, 15792, 15360, 15290, 15225, 15034, 14967,
    14720, 14743, 14582, 14619, 14382, 14629, 13930, 14273, 13960,
    14102, 13605, 13908, 13361, 13824, 13146, 13348, 13121, 13178,
    13341, 13059, 13077, 12838, 12865, 9131,
)


def validate_values(values: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    if len(values) != SENSOR_VALUES_COUNT:
        raise ValueError(f"values must contain exactly {SENSOR_VALUES_COUNT} items")
    normalized = tuple(values)
    for value in normalized:
        if not 0 <= value <= 65_535:
            raise ValueError("values must contain uint16 items")
    return normalized
```

- [ ] **Step 4: Run sample data tests to verify pass**

Run:

```bash
uv run pytest tests/test_sample_data.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/kc_sensor_mock/sample_data.py tests/test_sample_data.py
git commit -m "feat: add validated sample spectra data"
```

## Task 4: Implement Drop-Oldest Ring Buffer

**Files:**
- Create: `tests/test_ring_buffer.py`
- Create: `src/kc_sensor_mock/ring_buffer.py`

- [ ] **Step 1: Write failing ring buffer tests**

Create `tests/test_ring_buffer.py`:

```python
from kc_sensor_mock.ring_buffer import RingBuffer


def test_push_pop_fifo_when_not_full():
    buffer = RingBuffer[int](capacity=3)

    buffer.push(1)
    buffer.push(2)

    assert buffer.pop() == 1
    assert buffer.pop() == 2
    assert buffer.pop() is None
    assert buffer.dropped_total == 0


def test_push_drops_oldest_when_full():
    buffer = RingBuffer[int](capacity=2)

    buffer.push(1)
    buffer.push(2)
    buffer.push(3)

    assert buffer.dropped_total == 1
    assert buffer.pop() == 2
    assert buffer.pop() == 3


def test_capacity_must_be_positive():
    try:
        RingBuffer[int](capacity=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run ring buffer tests to verify failure**

Run:

```bash
uv run pytest tests/test_ring_buffer.py -v
```

Expected: FAIL because `kc_sensor_mock.ring_buffer` does not exist.

- [ ] **Step 3: Implement ring buffer**

Create `src/kc_sensor_mock/ring_buffer.py`:

```python
from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class RingBuffer(Generic[T]):
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._items: deque[T] = deque()
        self._capacity = capacity
        self._dropped_total = 0
        self._lock = Lock()

    @property
    def dropped_total(self) -> int:
        with self._lock:
            return self._dropped_total

    def push(self, item: T) -> None:
        with self._lock:
            if len(self._items) >= self._capacity:
                self._items.popleft()
                self._dropped_total += 1
            self._items.append(item)

    def pop(self) -> T | None:
        with self._lock:
            if not self._items:
                return None
            return self._items.popleft()
```

- [ ] **Step 4: Run ring buffer tests to verify pass**

Run:

```bash
uv run pytest tests/test_ring_buffer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/kc_sensor_mock/ring_buffer.py tests/test_ring_buffer.py
git commit -m "feat: add drop-oldest ring buffer"
```

## Task 5: Implement Config Loading and CLI Overrides

**Files:**
- Create: `tests/test_config.py`
- Create: `src/kc_sensor_mock/config.py`
- Create: `configs/default.toml`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
from pathlib import Path

from kc_sensor_mock.config import MockConfig, load_config


def test_load_config_from_toml(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
host = "127.0.0.1"
port = 9000
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
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config == MockConfig(
        host="127.0.0.1",
        port=9000,
        device_id=1,
        measurement_type=1,
        rate_hz=1000,
        mode="rate-controlled",
        ring_buffer_capacity=4096,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )


def test_cli_overrides_replace_config_values(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
host = "127.0.0.1"
port = 9000
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
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path, overrides={"port": 9100, "mode": "burst"})

    assert config.port == 9100
    assert config.mode == "burst"
```

- [ ] **Step 2: Run config tests to verify failure**

Run:

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL because `kc_sensor_mock.config` does not exist.

- [ ] **Step 3: Implement config module and default config**

Create `src/kc_sensor_mock/config.py`:

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MockConfig:
    host: str
    port: int
    device_id: int
    measurement_type: int
    rate_hz: int
    mode: str
    ring_buffer_capacity: int
    initial_sequence_number: int
    gps_latitude: float
    gps_longitude: float
    gps_altitude_m: float
    capture_path: Path | None


def load_config(path: Path, overrides: dict[str, Any] | None = None) -> MockConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if overrides:
        data.update({key: value for key, value in overrides.items() if value is not None})
    capture_path = data.get("capture_path") or None
    return MockConfig(
        host=str(data["host"]),
        port=int(data["port"]),
        device_id=int(data["device_id"]),
        measurement_type=int(data["measurement_type"]),
        rate_hz=int(data["rate_hz"]),
        mode=str(data["mode"]),
        ring_buffer_capacity=int(data["ring_buffer_capacity"]),
        initial_sequence_number=int(data["initial_sequence_number"]),
        gps_latitude=float(data["gps_latitude"]),
        gps_longitude=float(data["gps_longitude"]),
        gps_altitude_m=float(data["gps_altitude_m"]),
        capture_path=Path(capture_path) if capture_path else None,
    )
```

Create `configs/default.toml`:

```toml
host = "127.0.0.1"
port = 9000
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

- [ ] **Step 4: Run config tests to verify pass**

Run:

```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/kc_sensor_mock/config.py configs/default.toml tests/test_config.py
git commit -m "feat: add mock configuration loading"
```

## Task 6: Implement Record Generator

**Files:**
- Create: `tests/test_generator.py`
- Create: `src/kc_sensor_mock/generator.py`

- [ ] **Step 1: Write failing generator tests**

Create `tests/test_generator.py`:

```python
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.generator import RecordGenerator
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, SENSOR_VALUES_COUNT


def config() -> MockConfig:
    return MockConfig(
        host="127.0.0.1",
        port=9000,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="rate-controlled",
        ring_buffer_capacity=4096,
        initial_sequence_number=10,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )


def test_next_record_uses_config_and_sample_values():
    generator = RecordGenerator(config())

    record = generator.next_record(dropped_records_total=3)

    assert record.device_id == 1
    assert record.measurement_type == MEASUREMENT_TYPE_SPECTRA
    assert record.sequence_number == 10
    assert record.dropped_records_total == 3
    assert record.gps_latitude_e7 == 566_718_316
    assert record.gps_longitude_e7 == 242_391_946
    assert record.gps_altitude_mm == 35_000
    assert len(record.values) == SENSOR_VALUES_COUNT


def test_sequence_and_timestamps_increase():
    generator = RecordGenerator(config())

    first = generator.next_record(dropped_records_total=0)
    second = generator.next_record(dropped_records_total=0)

    assert second.sequence_number == first.sequence_number + 1
    assert second.sensor_timestamp_us > first.sensor_timestamp_us
    assert second.gps_timestamp_us > first.gps_timestamp_us
```

- [ ] **Step 2: Run generator tests to verify failure**

Run:

```bash
uv run pytest tests/test_generator.py -v
```

Expected: FAIL because `kc_sensor_mock.generator` does not exist.

- [ ] **Step 3: Implement generator**

Create `src/kc_sensor_mock/generator.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import (
    SensorRecord,
    scale_altitude_mm,
    scale_latitude_e7,
    scale_longitude_e7,
)
from kc_sensor_mock.sample_data import SAMPLE_VALUES


def epoch_us_now() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1_000_000)


class RecordGenerator:
    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._next_sequence = config.initial_sequence_number
        self._last_timestamp_us = 0

    def next_record(self, dropped_records_total: int) -> SensorRecord:
        now_us = max(epoch_us_now(), self._last_timestamp_us + 1)
        self._last_timestamp_us = now_us
        record = SensorRecord(
            device_id=self._config.device_id,
            measurement_type=self._config.measurement_type,
            sequence_number=self._next_sequence,
            dropped_records_total=dropped_records_total,
            sensor_timestamp_us=now_us,
            gps_timestamp_us=now_us,
            gps_latitude_e7=scale_latitude_e7(self._config.gps_latitude),
            gps_longitude_e7=scale_longitude_e7(self._config.gps_longitude),
            gps_altitude_mm=scale_altitude_mm(self._config.gps_altitude_m),
            values=SAMPLE_VALUES,
        )
        self._next_sequence += 1
        return record
```

- [ ] **Step 4: Run generator tests to verify pass**

Run:

```bash
uv run pytest tests/test_generator.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/kc_sensor_mock/generator.py tests/test_generator.py
git commit -m "feat: generate sample sensor records"
```

## Task 7: Implement TCP Server and Reference Client

**Files:**
- Create: `tests/test_server_client.py`
- Create: `src/kc_sensor_mock/server.py`
- Create: `src/kc_sensor_mock/client.py`

- [ ] **Step 1: Write failing server/client smoke test**

Create `tests/test_server_client.py`:

```python
from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA
from kc_sensor_mock.server import SensorServer


def config() -> MockConfig:
    return MockConfig(
        host="127.0.0.1",
        port=0,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="burst",
        ring_buffer_capacity=16,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )


def test_server_streams_records_to_reference_client():
    server = SensorServer(config())
    server.start()
    try:
        records = read_records(server.host, server.port, count=5, timeout_s=2.0)
    finally:
        server.stop()

    assert [record.sequence_number for record in records] == sorted(
        record.sequence_number for record in records
    )
    assert all(record.device_id == 1 for record in records)
```

- [ ] **Step 2: Run server/client test to verify failure**

Run:

```bash
uv run pytest tests/test_server_client.py -v
```

Expected: FAIL because `kc_sensor_mock.server` and `kc_sensor_mock.client` do not exist.

- [ ] **Step 3: Implement reference client**

Create `src/kc_sensor_mock/client.py`:

```python
from __future__ import annotations

import socket

from kc_sensor_mock.protocol import RECORD_SIZE, SensorRecord, decode_record


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("socket closed before full record was received")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_records(host: str, port: int, count: int, timeout_s: float = 5.0) -> list[SensorRecord]:
    records: list[SensorRecord] = []
    with socket.create_connection((host, port), timeout=timeout_s) as sock:
        sock.settimeout(timeout_s)
        for _ in range(count):
            records.append(decode_record(recv_exact(sock, RECORD_SIZE)))
    return records
```

- [ ] **Step 4: Implement single-client TCP server**

Create `src/kc_sensor_mock/server.py`:

```python
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.generator import RecordGenerator
from kc_sensor_mock.protocol import encode_record
from kc_sensor_mock.ring_buffer import RingBuffer


class SensorServer:
    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._generator = RecordGenerator(config)
        self._buffer = RingBuffer[bytes](config.ring_buffer_capacity)
        self._stop = threading.Event()
        self._producer_thread: threading.Thread | None = None
        self._server_thread: threading.Thread | None = None
        self._listener: socket.socket | None = None
        self.host = config.host
        self.port = config.port

    def start(self) -> None:
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((self.host, self.port))
        self._listener.listen(1)
        self.host, self.port = self._listener.getsockname()
        self._producer_thread = threading.Thread(target=self._produce, daemon=True)
        self._server_thread = threading.Thread(target=self._serve, daemon=True)
        self._producer_thread.start()
        self._server_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        for thread in (self._producer_thread, self._server_thread):
            if thread is not None:
                thread.join(timeout=2.0)

    def _produce(self) -> None:
        interval = 1.0 / self._config.rate_hz if self._config.rate_hz > 0 else 0.0
        while not self._stop.is_set():
            record = self._generator.next_record(self._buffer.dropped_total)
            self._buffer.push(encode_record(record))
            if self._config.mode == "rate-controlled":
                time.sleep(interval)

    def _serve(self) -> None:
        assert self._listener is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._listener.accept()
            except OSError:
                return
            with conn:
                self._stream_to_client(conn)

    def _stream_to_client(self, conn: socket.socket) -> None:
        capture_file = self._open_capture()
        try:
            while not self._stop.is_set():
                payload = self._buffer.pop()
                if payload is None:
                    time.sleep(0.001)
                    continue
                conn.sendall(payload)
                if capture_file is not None:
                    capture_file.write(payload)
        except OSError:
            return
        finally:
            if capture_file is not None:
                capture_file.close()

    def _open_capture(self):
        path: Path | None = self._config.capture_path
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.open("ab")
```

- [ ] **Step 5: Run server/client test to verify pass**

Run:

```bash
uv run pytest tests/test_server_client.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/kc_sensor_mock/server.py src/kc_sensor_mock/client.py tests/test_server_client.py
git commit -m "feat: stream records over tcp"
```

## Task 8: Implement Capture Test

**Files:**
- Create: `tests/test_capture.py`
- Modify: `src/kc_sensor_mock/server.py`

- [ ] **Step 1: Write failing capture test**

Create `tests/test_capture.py`:

```python
from pathlib import Path

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, RECORD_SIZE
from kc_sensor_mock.server import SensorServer


def test_capture_writes_exact_stream_bytes(tmp_path: Path):
    capture_path = tmp_path / "capture.bin"
    config = MockConfig(
        host="127.0.0.1",
        port=0,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="burst",
        ring_buffer_capacity=16,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=capture_path,
    )
    server = SensorServer(config)
    server.start()
    try:
        records = read_records(server.host, server.port, count=3, timeout_s=2.0)
    finally:
        server.stop()

    capture = capture_path.read_bytes()
    assert len(capture) >= 3 * RECORD_SIZE
    assert len(capture) % RECORD_SIZE == 0
    assert [record.sequence_number for record in records] == sorted(
        record.sequence_number for record in records
    )
```

- [ ] **Step 2: Run capture test**

Run:

```bash
uv run pytest tests/test_capture.py -v
```

Expected: PASS if Task 7 capture support is sufficient. If it fails because the file is not flushed before reading, update `_stream_to_client` to call `capture_file.flush()` after `capture_file.write(payload)`.

- [ ] **Step 3: Run capture and server tests together**

Run:

```bash
uv run pytest tests/test_capture.py tests/test_server_client.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add src/kc_sensor_mock/server.py tests/test_capture.py
git commit -m "test: verify raw stream capture"
```

## Task 9: Implement CLI Entry Points

**Files:**
- Create: `src/kc_sensor_mock/cli.py`

- [ ] **Step 1: Add CLI module**

Create `src/kc_sensor_mock/cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import load_config
from kc_sensor_mock.server import SensorServer


def server_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kc-sensor-mock")
    parser.add_argument("--config", type=Path, default=Path("configs/default.toml"))
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--device-id", type=int, dest="device_id")
    parser.add_argument("--measurement-type", type=int, dest="measurement_type")
    parser.add_argument("--rate-hz", type=int, dest="rate_hz")
    parser.add_argument("--mode", choices=["rate-controlled", "burst"])
    parser.add_argument("--ring-buffer-capacity", type=int, dest="ring_buffer_capacity")
    parser.add_argument("--capture-path", type=Path, dest="capture_path")
    return parser


def client_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kc-sensor-client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--count", type=int, default=10)
    return parser


def run_server_cli() -> None:
    args = server_parser().parse_args()
    overrides = {
        "host": args.host,
        "port": args.port,
        "device_id": args.device_id,
        "measurement_type": args.measurement_type,
        "rate_hz": args.rate_hz,
        "mode": args.mode,
        "ring_buffer_capacity": args.ring_buffer_capacity,
        "capture_path": args.capture_path,
    }
    config = load_config(args.config, overrides=overrides)
    server = SensorServer(config)
    server.start()
    print(f"streaming on {server.host}:{server.port}")
    try:
        while True:
            input()
    except (EOFError, KeyboardInterrupt):
        server.stop()


def run_client_cli() -> None:
    args = client_parser().parse_args()
    records = read_records(args.host, args.port, args.count)
    for record in records:
        print(
            f"sequence={record.sequence_number} "
            f"device_id={record.device_id} "
            f"measurement_type={record.measurement_type} "
            f"dropped={record.dropped_records_total}"
        )
```

- [ ] **Step 2: Run CLI help**

Run:

```bash
uv run kc-sensor-mock --help
uv run kc-sensor-client --help
```

Expected: both commands print argparse help text and exit with code 0.

- [ ] **Step 3: Run all automated tests**

Run:

```bash
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add src/kc_sensor_mock/cli.py pyproject.toml
git commit -m "feat: add server and client cli"
```

## Task 10: Add Manual Performance Check

**Files:**
- Create: `tests/perf/test_stream_rate.py`

- [ ] **Step 1: Add performance test script**

Create `tests/perf/test_stream_rate.py`:

```python
from __future__ import annotations

import time

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, RECORD_SIZE
from kc_sensor_mock.server import SensorServer


def test_stream_rate_manual():
    count = 1_000
    config = MockConfig(
        host="127.0.0.1",
        port=0,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="rate-controlled",
        ring_buffer_capacity=4096,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )
    server = SensorServer(config)
    server.start()
    started = time.perf_counter()
    try:
        records = read_records(server.host, server.port, count=count, timeout_s=5.0)
    finally:
        server.stop()
    elapsed = time.perf_counter() - started
    records_per_second = len(records) / elapsed
    bytes_per_second = records_per_second * RECORD_SIZE
    print(f"{records_per_second:.1f} records/s, {bytes_per_second:.1f} bytes/s")
    assert len(records) == count
```

- [ ] **Step 2: Run the performance check manually**

Run:

```bash
uv run pytest tests/perf/test_stream_rate.py --run-perf -s -v
```

Expected: PASS and prints achieved records per second plus bytes per second. This test is not part of the normal reliability gate because OS scheduling can vary.

- [ ] **Step 3: Run normal test suite**

Run:

```bash
uv run pytest tests -v --ignore=tests/perf
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add tests/perf/test_stream_rate.py
git commit -m "test: add manual stream performance check"
```

## Task 11: Final Verification

**Files:**
- Modify: `README.md` if `uv init` created one, otherwise create it.

- [ ] **Step 1: Add usage documentation**

Create or update `README.md`:

```markdown
# KC Sensor Mock

Python v1 mock for an STM-style sensor device. It streams repeated fixed-size 632-byte little-endian records over TCP.

## Protocol

The TCP stream contains repeated records with no delimiter, header, length prefix, magic value, or checksum.

Python struct format:

```text
<HHIIQQiii296H
```

Consumers must read exactly 632 bytes per record.

## Run

```bash
uv run kc-sensor-mock --config configs/default.toml
```

## Read Records

```bash
uv run kc-sensor-client --host 127.0.0.1 --port 9000 --count 10
```

## Test

```bash
uv run pytest tests -v --ignore=tests/perf
uv run pytest tests/perf/test_stream_rate.py --run-perf -s -v
```
```

- [ ] **Step 2: Run final normal tests**

Run:

```bash
uv run pytest tests -v --ignore=tests/perf
```

Expected: PASS.

- [ ] **Step 3: Run CLI help verification**

Run:

```bash
uv run kc-sensor-mock --help
uv run kc-sensor-client --help
```

Expected: both commands print help text and exit with code 0.

- [ ] **Step 4: Run manual performance check**

Run:

```bash
uv run pytest tests/perf/test_stream_rate.py --run-perf -s -v
```

Expected: PASS and reports throughput.

- [ ] **Step 5: Commit**

Run:

```bash
git add README.md
git commit -m "docs: document sensor mock usage"
```

## Self-Review Notes

- Spec coverage: protocol, generation, ring buffer, TCP streaming, config, capture, reference client, tests, and performance validation are covered.
- Explicit exclusions are preserved: no TCP frame header, no delimiters, no checksums, no variable-length records, no multi-client fan-out.
- Type consistency: record fields match `<HHIIQQiii296H`; record size remains 632 bytes; measurement types remain `1` and `2`.
- Testing: every implementation task starts with failing tests except CLI and README tasks, which use command verification because their behavior is command-line integration.
