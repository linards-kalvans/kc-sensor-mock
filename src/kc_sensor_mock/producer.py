"""Sensor producer: outbound TCP client that streams encoded records to a consumer."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import BinaryIO

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.generator import RecordGenerator
from kc_sensor_mock.protocol import encode_record
from kc_sensor_mock.ring_buffer import RingBuffer


class SensorProducerClient:
    """Outbound producer that connects to a consumer endpoint and streams records."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._generator = RecordGenerator(config)
        self._ring_buffer = RingBuffer[bytes](config.ring_buffer_capacity)
        self._stop_event = threading.Event()
        self._producer_thread: threading.Thread | None = None
        self._sender_thread: threading.Thread | None = None
        self._capture_file: BinaryIO | None = None
        self._capture_error: OSError | None = None
        self._state_lock = threading.Lock()

    def start(self) -> None:
        with self._state_lock:
            if self._producer_thread is not None:
                raise RuntimeError("producer already started")

            self._stop_event.clear()

            if self._config.capture_path is not None:
                capture_path = self._config.capture_path
                capture_path.parent.mkdir(parents=True, exist_ok=True)
                self._capture_file = capture_path.open("wb")

            self._producer_thread = threading.Thread(
                target=self._produce,
                name="kc-sensor-mock-producer",
                daemon=True,
            )
            self._sender_thread = threading.Thread(
                target=self._send_loop,
                name="kc-sensor-mock-sender",
                daemon=True,
            )
            self._producer_thread.start()
            self._sender_thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        producer_thread = self._producer_thread
        sender_thread = self._sender_thread
        self._producer_thread = None
        self._sender_thread = None

        if producer_thread is not None:
            producer_thread.join(timeout=2.0)
        if sender_thread is not None:
            sender_thread.join(timeout=2.0)

        capture_file = self._capture_file
        self._capture_file = None
        if capture_file is not None:
            capture_file.close()

        if self._capture_error is not None:
            capture_error = self._capture_error
            self._capture_error = None
            raise RuntimeError("capture write failed") from capture_error

    def _produce(self) -> None:
        while not self._stop_event.is_set():
            record = self._generator.next_record(self._ring_buffer.dropped_total)
            self._ring_buffer.push(encode_record(record))
            if self._config.mode == "rate-controlled":
                time.sleep(1.0 / self._config.rate_hz)

    def _send_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn = self._connect()
            except OSError:
                time.sleep(0.1)
                continue

            try:
                self._stream_to_consumer(conn)
            except OSError:
                pass
            finally:
                conn.close()

    def _connect(self) -> socket.socket:
        host = self._config.consumer_host
        port = self._config.consumer_port
        if host is None or port is None:
            raise OSError("consumer_host and consumer_port must be set")
        return socket.create_connection((host, port), timeout=2.0)

    def _stream_to_consumer(self, conn: socket.socket) -> None:
        while not self._stop_event.is_set():
            payload = self._ring_buffer.pop()
            if payload is None:
                time.sleep(0.001)
                continue

            capture_position = self._capture_position()
            if capture_position is None and self._capture_file is not None:
                return

            if not self._write_capture_payload(payload):
                return

            try:
                conn.sendall(payload)
            except OSError:
                if capture_position is not None and not self._rollback_capture_payload(capture_position):
                    return
                return

    def _capture_position(self) -> int | None:
        capture_file = self._capture_file
        if capture_file is None:
            return None

        try:
            return capture_file.tell()
        except OSError as exc:
            self._capture_error = exc
            self._stop_event.set()
            return None

    def _write_capture_payload(self, payload: bytes) -> bool:
        capture_file = self._capture_file
        if capture_file is None:
            return True

        try:
            capture_file.write(payload)
            capture_file.flush()
        except OSError as exc:
            self._capture_error = exc
            self._stop_event.set()
            return False

        return True

    def _rollback_capture_payload(self, position: int) -> bool:
        capture_file = self._capture_file
        if capture_file is None:
            return True

        try:
            capture_file.truncate(position)
            capture_file.seek(position)
            capture_file.flush()
        except OSError as exc:
            self._capture_error = exc
            self._stop_event.set()
            return False

        return True
