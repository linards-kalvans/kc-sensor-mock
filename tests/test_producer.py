"""Tests for producer runtime: outbound connection, record stream, reconnect, capture."""

from __future__ import annotations

import socket
import time
from pathlib import Path

import pytest

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import (
    MEASUREMENT_TYPE_SPECTRA,
    RECORD_SIZE,
    SensorRecord,
    decode_record,
)


def _make_config(
    consumer_host: str = "127.0.0.1",
    consumer_port: int = 0,
    capture_path: Path | None = None,
    ring_buffer_capacity: int = 64,
    bind_host: str = "127.0.0.1",
    bind_port: int = 0,
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
        ring_buffer_capacity=ring_buffer_capacity,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=capture_path,
    )


# --- AC-1: Producer does NOT bind a listener ---

def test_producer_start_does_not_bind_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_calls: list[tuple[str, int]] = []

    class FakeSocket:
        def setsockopt(self, *args: object, **kwargs: object) -> None:
            pass

        def bind(self, address: tuple[str, int]) -> None:
            bind_calls.append(address)

        def connect(self, *args: object) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeSocketModule:
        AF_INET = socket.AF_INET
        SOCK_STREAM = socket.SOCK_STREAM
        SOL_SOCKET = socket.SOL_SOCKET
        SO_REUSEADDR = socket.SO_REUSEADDR

        def socket(self, *args: object, **kwargs: object) -> FakeSocket:
            return FakeSocket()

        def __getattr__(self, name: str) -> object:
            return getattr(socket, name)

    monkeypatch.setattr("kc_sensor_mock.producer.socket", FakeSocketModule())

    producer_client = producer.SensorProducerClient(
        _make_config(consumer_host="127.0.0.1", consumer_port=9999)
    )
    producer_client.start()
    time.sleep(0.2)
    producer_client.stop()

    assert bind_calls == [], "producer must not bind a listening socket"


# --- AC-2: Producer connects outward to configured consumer endpoint ---

def test_producer_connects_outward_to_consumer(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2.0)
    host, port = listener.getsockname()

    producer_client = producer.SensorProducerClient(
        _make_config(
            consumer_host=host,
            consumer_port=port,
            capture_path=tmp_path / "capture.bin",
        )
    )
    producer_client.start()

    try:
        consumer_socket, _ = listener.accept()
        consumer_socket.settimeout(1.0)
        data = consumer_socket.recv(RECORD_SIZE)
    finally:
        producer_client.stop()
        listener.close()

    assert len(data) == RECORD_SIZE


# --- AC-3: Stream contains only encoded records, no preamble ---

def test_producer_stream_has_no_preamble() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2.0)
    host, port = listener.getsockname()

    producer_client = producer.SensorProducerClient(
        _make_config(consumer_host=host, consumer_port=port)
    )
    producer_client.start()

    try:
        consumer_socket, _ = listener.accept()
        consumer_socket.settimeout(1.0)
        first_chunk = consumer_socket.recv(RECORD_SIZE)
    finally:
        producer_client.stop()
        listener.close()

    decoded = decode_record(first_chunk)
    assert isinstance(decoded, SensorRecord)


# --- AC-4: Producer reconnects on disconnect ---

def test_producer_reconnects_on_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    connect_count = 0

    class FakeConnection:
        def sendall(self, data: bytes) -> None:
            raise OSError("consumer disconnected")

        def close(self) -> None:
            pass

    def fake_create_connection(address: tuple[str, int], timeout: float) -> FakeConnection:
        nonlocal connect_count
        connect_count += 1
        if connect_count <= 3:
            return FakeConnection()
        raise ConnectionRefusedError("no consumer")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    producer_client = producer.SensorProducerClient(
        _make_config(consumer_host="127.0.0.1", consumer_port=19876)
    )
    producer_client.start()
    time.sleep(0.3)
    producer_client.stop()

    assert connect_count >= 2


# --- AC-4b: Producer keeps generating while disconnected and drops oldest ---

def test_producer_drops_oldest_while_disconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_create_connection(address: tuple[str, int], timeout: float) -> socket.socket:
        raise ConnectionRefusedError("no consumer")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    producer_client = producer.SensorProducerClient(
        _make_config(
            consumer_host="127.0.0.1",
            consumer_port=19877,
            ring_buffer_capacity=2,
        )
    )
    producer_client.start()
    time.sleep(0.2)
    producer_client.stop()

    assert producer_client._ring_buffer.dropped_total > 0, (
        "producer must continue generating while disconnected until drop-oldest behavior occurs"
    )


# --- AC-7: Producer-side capture bytes equal bytes delivered to consumer ---

def test_capture_bytes_match_consumer_delivered_bytes(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2.0)
    host, port = listener.getsockname()

    capture_path = tmp_path / "capture.bin"
    producer_client = producer.SensorProducerClient(
        _make_config(
            consumer_host=host,
            consumer_port=port,
            capture_path=capture_path,
        )
    )
    producer_client.start()

    try:
        consumer_socket, _ = listener.accept()
        consumer_socket.settimeout(1.0)
        received = consumer_socket.recv(RECORD_SIZE * 3)
    finally:
        producer_client.stop()
        listener.close()

    captured = capture_path.read_bytes()
    assert received
    assert captured.startswith(received)


# --- AC-8: Failed send does not leave unsent bytes in capture file ---

def test_failed_send_does_not_keep_unsent_bytes_in_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeConnection:
        def sendall(self, data: bytes) -> None:
            raise OSError("consumer disconnected")

        def close(self) -> None:
            pass

    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: FakeConnection())

    capture_path = tmp_path / "capture.bin"
    producer_client = producer.SensorProducerClient(
        _make_config(
            consumer_host="127.0.0.1",
            consumer_port=19000,
            capture_path=capture_path,
        )
    )
    producer_client.start()
    time.sleep(0.2)
    producer_client.stop()

    assert capture_path.read_bytes() == b""


import kc_sensor_mock.producer as producer  # noqa: E402
