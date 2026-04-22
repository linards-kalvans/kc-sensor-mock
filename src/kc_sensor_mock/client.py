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
    validate_record_stream(records)
    return records


def _uint32_delta(current: int, previous: int) -> int:
    return (current - previous) & 0xFFFFFFFF


def validate_record_stream(records: list[SensorRecord]) -> None:
    if not records:
        return

    previous = records[0]
    if len(previous.values) != 296:
        raise ValueError("values must contain exactly 296 items")

    for current in records[1:]:
        if len(current.values) != 296:
            raise ValueError("values must contain exactly 296 items")

        sequence_delta = _uint32_delta(current.sequence_number, previous.sequence_number)
        if sequence_delta == 0:
            raise ValueError("sequence_number must increase between records")
        if sequence_delta > 0x7FFFFFFF:
            raise ValueError("sequence_number moved backwards")

        dropped_delta = _uint32_delta(
            current.dropped_records_total,
            previous.dropped_records_total,
        )
        if dropped_delta > 0x7FFFFFFF:
            raise ValueError("dropped_records_total moved backwards")

        if current.sensor_timestamp_us <= previous.sensor_timestamp_us:
            raise ValueError("sensor_timestamp_us must strictly increase")
        if current.gps_timestamp_us <= previous.gps_timestamp_us:
            raise ValueError("gps_timestamp_us must strictly increase")

        previous = current
