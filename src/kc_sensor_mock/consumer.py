"""Sensor consumer: inbound TCP listener that accepts one producer at a time."""

from __future__ import annotations

import socket
import struct
import threading
import time

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import RECORD_SIZE, decode_record


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Read exactly *size* bytes from *sock*.

    Raises ``ConnectionError`` if the socket closes before *size* bytes are read.
    """
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError(
                f"expected {size} bytes but socket closed after {len(data)}"
            )
        data.extend(chunk)
    return bytes(data)


class SensorConsumerServer:
    """Inbound consumer that binds a listener and accepts one producer at a time."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._listener: socket.socket | None = None
        self._server_thread: threading.Thread | None = None
        self.host: str = config.bind_host or "127.0.0.1"
        self.port: int = 0

    def start(self) -> None:
        self._stop_event.clear()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_host = self._config.bind_host or "127.0.0.1"
        bind_port = self._config.bind_port if self._config.bind_port is not None else 0
        listener.bind((bind_host, bind_port))
        listener.listen(1)
        listener.settimeout(0.2)
        self._listener = listener
        self.host, self.port = listener.getsockname()[:2]

        self._server_thread = threading.Thread(
            target=self._accept_loop,
            name="kc-sensor-mock-consumer",
            daemon=True,
        )
        self._server_thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.close()

        server_thread = self._server_thread
        self._server_thread = None
        if server_thread is not None:
            server_thread.join(timeout=2.0)

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            listener = self._listener
            if listener is None:
                break

            try:
                producer_socket, _ = listener.accept()
            except (OSError, socket.timeout):
                continue

            with producer_socket:
                self._read_from_producer(producer_socket)

    def _read_from_producer(self, producer_socket: socket.socket) -> None:
        while not self._stop_event.is_set():
            try:
                payload = recv_exact(producer_socket, RECORD_SIZE)
            except ConnectionError:
                return
            try:
                record = decode_record(payload)
            except (ValueError, struct.error):
                # Malformed record — close this connection and continue
                return
            # Consumer can decode received records (validation done in decode_record)
