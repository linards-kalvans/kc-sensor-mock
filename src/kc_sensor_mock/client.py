from __future__ import annotations

import socket
from contextlib import closing

from kc_sensor_mock.protocol import RECORD_SIZE, SensorRecord, decode_record


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("socket closed before receiving expected bytes")
        data.extend(chunk)
    return bytes(data)


def read_records(
    host: str,
    port: int,
    count: int,
    timeout_s: float = 5.0,
) -> list[SensorRecord]:
    records: list[SensorRecord] = []
    with closing(socket.create_connection((host, port), timeout=timeout_s)) as sock:
        sock.settimeout(timeout_s)
        for _ in range(count):
            payload = recv_exact(sock, RECORD_SIZE)
            records.append(decode_record(payload))
    return records
