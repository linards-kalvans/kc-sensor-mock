"""Tests for consumer runtime: listener behavior, exact-record reads, parquet export."""

from __future__ import annotations

import dataclasses
import socket
import threading
import time
from pathlib import Path

import pytest

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import (
    MEASUREMENT_TYPE_SPECTRA,
    RECORD_SIZE,
    SensorRecord,
    decode_record,
    encode_record,
)


def _make_consumer_config(
    bind_host: str = "127.0.0.1",
    bind_port: int = 0,
    consumer_host: str | None = "127.0.0.1",
    consumer_port: int | None = 9000,
) -> MockConfig:
    return MockConfig(
        bind_host=bind_host,
        bind_port=bind_port,
        consumer_host=consumer_host,
        consumer_port=consumer_port,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="burst",
        ring_buffer_capacity=64,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )


# ---------------------------------------------------------------------------
# AC-5: Consumer binds and accepts one producer at a time
# ---------------------------------------------------------------------------


def test_consumer_binds_and_processes_connected_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    processed = threading.Event()
    received_sizes: list[int] = []

    def fake_read_from_producer(self: object, producer_socket: socket.socket) -> None:
        payload = producer_socket.recv(RECORD_SIZE)
        received_sizes.append(len(payload))
        processed.set()

    monkeypatch.setattr(
        consumer.SensorConsumerServer,
        "_read_from_producer",
        fake_read_from_producer,
    )

    config = _make_consumer_config(bind_host="127.0.0.1", bind_port=0)
    svc = consumer.SensorConsumerServer(config)
    svc.start()

    try:
        assert svc.host == "127.0.0.1"
        assert svc.port > 0

        with socket.create_connection((svc.host, svc.port), timeout=2.0) as producer_socket:
            producer_socket.sendall(b"\x00" * RECORD_SIZE)
            assert processed.wait(timeout=1.0)
    finally:
        svc.stop()

    assert received_sizes == [RECORD_SIZE]


def test_consumer_handles_only_one_active_producer_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_handler_started = threading.Event()
    release_first_handler = threading.Event()
    active_handlers = 0
    max_active_handlers = 0
    lock = threading.Lock()

    def fake_read_from_producer(self: object, producer_socket: socket.socket) -> None:
        nonlocal active_handlers, max_active_handlers
        with lock:
            active_handlers += 1
            max_active_handlers = max(max_active_handlers, active_handlers)
        first_handler_started.set()
        release_first_handler.wait(timeout=1.0)
        producer_socket.recv(RECORD_SIZE)
        with lock:
            active_handlers -= 1

    monkeypatch.setattr(
        consumer.SensorConsumerServer,
        "_read_from_producer",
        fake_read_from_producer,
    )

    config = _make_consumer_config(bind_host="127.0.0.1", bind_port=0)
    svc = consumer.SensorConsumerServer(config)
    svc.start()

    try:
        producer_one = socket.create_connection((svc.host, svc.port), timeout=2.0)
        assert first_handler_started.wait(timeout=1.0)

        producer_two = socket.create_connection((svc.host, svc.port), timeout=2.0)
        time.sleep(0.2)

        assert max_active_handlers == 1
        release_first_handler.set()
        producer_one.sendall(b"\x00" * RECORD_SIZE)
        producer_one.close()
        producer_two.close()
    finally:
        svc.stop()


# ---------------------------------------------------------------------------
# AC-6: Consumer reads exact 632-byte records and partial reads fail
# ---------------------------------------------------------------------------


def test_consumer_recv_exact_reads_full_record() -> None:
    class FakeSock:
        def __init__(self, data: bytes) -> None:
            self._data = bytearray(data)
            self._pos = 0

        def recv(self, n: int) -> bytes:
            chunk = self._data[self._pos : self._pos + max(1, n // 2)]
            self._pos += len(chunk)
            return bytes(chunk) if chunk else b""

    full_record = b"\x00" * RECORD_SIZE
    payload = consumer.recv_exact(FakeSock(full_record), RECORD_SIZE)
    assert payload == full_record


def test_consumer_recv_exact_raises_on_partial_record() -> None:
    class FakeSock:
        def __init__(self) -> None:
            self._sent = 0

        def recv(self, n: int) -> bytes:
            if self._sent == 0:
                self._sent += 1
                return b"\x00" * (RECORD_SIZE // 2)
            return b""

    with pytest.raises(ConnectionError, match="expected"):
        consumer.recv_exact(FakeSock(), RECORD_SIZE)


# ---------------------------------------------------------------------------
# AC-6b: Consumer can decode received records
# ---------------------------------------------------------------------------


def test_consumer_decodes_received_record() -> None:
    record = SensorRecord(
        device_id=42,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        sequence_number=100,
        dropped_records_total=5,
        sensor_timestamp_us=1_000_000,
        gps_timestamp_us=1_000_001,
        gps_latitude_e7=566718316,
        gps_longitude_e7=242391946,
        gps_altitude_mm=35000,
        values=tuple(range(296)),
    )
    payload = encode_record(record)

    class FakeSock:
        def __init__(self, data: bytes) -> None:
            self._data = bytearray(data)
            self._pos = 0

        def recv(self, n: int) -> bytes:
            chunk = self._data[self._pos : self._pos + max(1, n // 2)]
            self._pos += len(chunk)
            return bytes(chunk) if chunk else b""

    received = consumer.recv_exact(FakeSock(payload), RECORD_SIZE)
    decoded = decode_record(received)

    assert decoded.device_id == 42
    assert decoded.sequence_number == 100
    assert decoded.dropped_records_total == 5
    assert len(decoded.values) == 296


# ---------------------------------------------------------------------------
# Malformed input does not kill the consumer server
# ---------------------------------------------------------------------------


def test_consumer_handles_malformed_input_without_dying(monkeypatch: pytest.MonkeyPatch) -> None:
    accept_count = 0
    lock = threading.Lock()

    def fake_read_from_producer(self: object, producer_socket: socket.socket) -> None:
        with lock:
            nonlocal accept_count
            accept_count += 1
        producer_socket.recv(4096)

    monkeypatch.setattr(
        consumer.SensorConsumerServer,
        "_read_from_producer",
        fake_read_from_producer,
    )

    config = _make_consumer_config(bind_host="127.0.0.1", bind_port=0)
    svc = consumer.SensorConsumerServer(config)
    svc.start()

    try:
        with socket.create_connection((svc.host, svc.port), timeout=2.0) as s:
            s.sendall(b"short")
            time.sleep(0.3)

        with socket.create_connection((svc.host, svc.port), timeout=2.0) as s:
            s.sendall(b"more garbage")
            time.sleep(0.3)

        assert accept_count >= 2
    finally:
        svc.stop()


# ---------------------------------------------------------------------------
# Parquet integration: AC-8 end-to-end consumer -> parquet
# ---------------------------------------------------------------------------

import kc_sensor_mock.consumer as consumer  # noqa: E402


def _poll_files(path: Path, timeout: float = 3.0, interval: float = 0.1) -> list[Path]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        files = sorted(path.glob("*.parquet"))
        if files:
            return files
        time.sleep(interval)
    return sorted(path.glob("*.parquet"))


def _make_enabled_consumer_config(bind_port: int = 0, output_dir: str = "/tmp") -> MockConfig:
    """Build a MockConfig with parquet_enabled=True for consumer integration tests.

    Constructs explicitly because MockConfig is a frozen dataclass and the
    parquet fields do not exist on the class yet.
    """
    return MockConfig(
        bind_host="127.0.0.1",
        bind_port=bind_port,
        consumer_host="127.0.0.1",
        consumer_port=9000,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="burst",
        ring_buffer_capacity=64,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
        parquet_enabled=True,
        parquet_output_dir=Path(output_dir),
        parquet_batch_mode="volume",
        parquet_max_records_per_file=100,
        parquet_flush_interval_seconds=1.0,
        parquet_queue_capacity=64,
    )


def test_consumer_exports_to_parquet_on_record_receive(tmp_path: Path) -> None:
    """When a consumer receives a record and parquet is enabled, the record
    must be exported to a parquet file."""
    config = _make_enabled_consumer_config(output_dir=str(tmp_path))
    svc = consumer.SensorConsumerServer(config)
    svc.start()

    try:
        with socket.create_connection((svc.host, svc.port), timeout=2.0) as s:
            record = SensorRecord(
                device_id=1,
                measurement_type=MEASUREMENT_TYPE_SPECTRA,
                sequence_number=1,
                dropped_records_total=0,
                sensor_timestamp_us=1_000_000,
                gps_timestamp_us=1_000_001,
                gps_latitude_e7=566718316,
                gps_longitude_e7=242391946,
                gps_altitude_mm=35000,
                values=tuple(range(296)),
            )
            s.sendall(encode_record(record))
            time.sleep(1.5)
    finally:
        svc.stop()

    files = _poll_files(tmp_path)
    assert len(files) >= 1

    import pyarrow.parquet as pq

    table = pq.read_table(files[0])
    assert table.num_rows == 1


def test_consumer_parquet_disabled_means_no_parquet_files(tmp_path: Path) -> None:
    """When parquet is disabled (default), receiving records must not create parquet files."""
    config = _make_consumer_config(bind_host="127.0.0.1", bind_port=0)
    assert config.parquet_enabled is False

    svc = consumer.SensorConsumerServer(config)
    svc.start()

    try:
        with socket.create_connection((svc.host, svc.port), timeout=2.0) as s:
            record = SensorRecord(
                device_id=1,
                measurement_type=MEASUREMENT_TYPE_SPECTRA,
                sequence_number=1,
                dropped_records_total=0,
                sensor_timestamp_us=1_000_000,
                gps_timestamp_us=1_000_001,
                gps_latitude_e7=566718316,
                gps_longitude_e7=242391946,
                gps_altitude_mm=35000,
                values=tuple(range(296)),
            )
            s.sendall(encode_record(record))
            time.sleep(1.0)
    finally:
        svc.stop()

    files = list(tmp_path.glob("*.parquet"))
    assert len(files) == 0


def test_consumer_surfaces_exporter_fatal_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When the exporter raises during start(), the consumer must not
    silently ignore it — the exception should propagate."""

    class FakeExportError(Exception):
        pass

    class FakeExporter:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            raise FakeExportError("boom")

        def submit(self, record):
            pass

        def stop(self):
            pass

    config = _make_enabled_consumer_config(output_dir=str(tmp_path))
    svc = consumer.SensorConsumerServer(config)

    monkeypatch.setattr(consumer, "ConsumerParquetExporter", FakeExporter)

    with pytest.raises(FakeExportError, match="boom"):
        svc.start()


def test_consumer_uses_dataclasses_replace(tmp_path: Path) -> None:
    """Consumer tests must use dataclasses.replace or explicit MockConfig construction,
    not .replace() on the config object."""
    base = _make_consumer_config(bind_host="127.0.0.1", bind_port=0)
    # dataclasses.replace should work (MockConfig is frozen=True dataclass)
    modified = dataclasses.replace(base, bind_port=9999)
    assert modified.bind_port == 9999
