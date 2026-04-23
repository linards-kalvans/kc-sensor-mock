"""Tests for consumer runtime: listener behavior and exact-record reads."""

from __future__ import annotations

import socket
import threading
import time

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


# --- AC-5: Consumer binds and accepts one producer at a time ---

def test_consumer_binds_and_processes_connected_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consumer must invoke its producer-read path after a producer connects."""
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
            assert processed.wait(timeout=1.0), (
                "consumer must process a connected producer via _read_from_producer"
            )
    finally:
        svc.stop()

    assert received_sizes == [RECORD_SIZE]


def test_consumer_handles_only_one_active_producer_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consumer must not run two producer handlers concurrently."""
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

        assert max_active_handlers == 1, (
            "consumer must not process multiple producer connections concurrently"
        )

        release_first_handler.set()
        producer_one.sendall(b"\x00" * RECORD_SIZE)
        producer_one.close()
        producer_two.close()
    finally:
        svc.stop()


# --- AC-6: Consumer reads exact 632-byte records and partial reads fail in helper ---

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


# --- AC-6b: Consumer can decode received records ---

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


# --- Malformed input does not kill the consumer server ---

def test_consumer_handles_malformed_input_without_dying(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed payload must close that producer connection and keep accepting."""
    accept_count = 0
    lock = threading.Lock()

    def fake_read_from_producer(self: object, producer_socket: socket.socket) -> None:
        with lock:
            nonlocal accept_count
            accept_count += 1
        # Just drain whatever is on the socket; malformed data will cause
        # decode_record to raise ValueError, which _read_from_producer must
        # catch so the accept loop continues.
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
        # Connect producer 1 with malformed data (too short).
        with socket.create_connection((svc.host, svc.port), timeout=2.0) as s:
            s.sendall(b"short")
            time.sleep(0.3)

        # Connect producer 2 — if server died this would hang/timeout.
        with socket.create_connection((svc.host, svc.port), timeout=2.0) as s:
            s.sendall(b"more garbage")
            time.sleep(0.3)

        assert accept_count >= 2, (
            f"server must accept multiple producers after malformed input; got {accept_count}"
        )
    finally:
        svc.stop()


import kc_sensor_mock.consumer as consumer  # noqa: E402
