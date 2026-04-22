from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import Mock

import pytest

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, SensorRecord, encode_record
from kc_sensor_mock.server import SensorServer


def _record(
    sequence_number: int,
    dropped_records_total: int,
    sensor_timestamp_us: int,
    gps_timestamp_us: int,
    values: tuple[int, ...] = tuple(range(296)),
) -> SensorRecord:
    return SensorRecord(
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        sequence_number=sequence_number,
        dropped_records_total=dropped_records_total,
        sensor_timestamp_us=sensor_timestamp_us,
        gps_timestamp_us=gps_timestamp_us,
        gps_latitude_e7=1,
        gps_longitude_e7=2,
        gps_altitude_mm=3,
        values=values,
    )


def test_server_streams_records_to_reference_client() -> None:
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
        capture_path=None,
    )

    server = SensorServer(config)

    try:
        server.start()
        records = read_records(
            server.host,
            server.port,
            count=5,
            timeout_s=2.0,
        )
    finally:
        server.stop()

    sequences = [record.sequence_number for record in records]
    assert len(records) == 5
    assert sequences == sorted(sequences)
    assert all(record.device_id == 1 for record in records)


def test_validate_record_stream_rejects_duplicate_sequence() -> None:
    from kc_sensor_mock.client import validate_record_stream

    records = [
        _record(10, 0, 100, 100),
        _record(10, 0, 101, 101),
    ]

    with pytest.raises(ValueError, match="sequence"):
        validate_record_stream(records)


def test_validate_record_stream_rejects_decreasing_timestamps() -> None:
    from kc_sensor_mock.client import validate_record_stream

    records = [
        _record(10, 0, 100, 100),
        _record(11, 0, 100, 99),
    ]

    with pytest.raises(ValueError, match="timestamp"):
        validate_record_stream(records)


def test_validate_record_stream_accepts_equal_timestamps() -> None:
    from kc_sensor_mock.client import validate_record_stream

    records = [
        _record(10, 0, 100, 100),
        _record(11, 0, 100, 100),
    ]

    validate_record_stream(records)


def test_validate_record_stream_rejects_wrong_values_length() -> None:
    from kc_sensor_mock.client import validate_record_stream

    records = [_record(10, 0, 100, 100, values=tuple(range(295)))]

    with pytest.raises(ValueError, match="296"):
        validate_record_stream(records)


def test_capture_write_failure_stops_server(monkeypatch, tmp_path: Path) -> None:
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
        capture_path=tmp_path / "capture.bin",
    )

    server = SensorServer(config)

    payloads: list[bytes] = []
    state = {"size": 0}

    class FakeRingBuffer:
        def __init__(self) -> None:
            self._items = [b"abc"]

        def pop(self) -> bytes | None:
            if self._items:
                return self._items.pop(0)
            return None

    class FakeCapture:
        def tell(self) -> int:
            return state["size"]

        def write(self, payload: bytes) -> None:
            payloads.append(payload)
            state["size"] += len(payload)
            raise OSError("disk full")

        def flush(self) -> None:
            raise AssertionError("flush should not be called after write failure")

        def truncate(self, position: int) -> None:
            state["size"] = position

        def seek(self, position: int) -> int:
            state["size"] = position
            return position

        def seek(self, position: int) -> int:
            state["size"] = position
            return position

        def seek(self, position: int) -> int:
            state["size"] = position
            return position

    fake_socket = Mock()
    fake_socket.sendall = Mock()
    monkeypatch.setattr(server, "_ring_buffer", FakeRingBuffer())
    monkeypatch.setattr(server, "_capture_file", FakeCapture())

    server._stream_to_client(fake_socket)

    assert payloads == [b"abc"]
    fake_socket.sendall.assert_not_called()
    assert server._stop_event.is_set()
    assert server._capture_error is not None


def test_capture_rolls_back_when_send_fails(monkeypatch, tmp_path: Path) -> None:
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
        capture_path=tmp_path / "capture.bin",
    )

    server = SensorServer(config)
    written: list[bytes] = []
    state = {"size": 0}

    class FakeRingBuffer:
        def __init__(self) -> None:
            self._items = [b"payload"]

        def pop(self) -> bytes | None:
            if self._items:
                return self._items.pop(0)
            return None

    class FakeCapture:
        def tell(self) -> int:
            return state["size"]

        def write(self, payload: bytes) -> None:
            written.append(payload)
            state["size"] += len(payload)

        def flush(self) -> None:
            pass

        def truncate(self, position: int) -> None:
            state["size"] = position

        def seek(self, position: int) -> int:
            state["size"] = position
            return position

    fake_socket = Mock()
    fake_socket.sendall.side_effect = OSError("client disconnected")
    monkeypatch.setattr(server, "_ring_buffer", FakeRingBuffer())
    monkeypatch.setattr(server, "_capture_file", FakeCapture())

    server._stream_to_client(fake_socket)

    assert written == [b"payload"]
    assert state["size"] == 0
    assert server._capture_error is None
    assert server._stop_event.is_set() is False
    fake_socket.sendall.assert_called_once_with(b"payload")


def test_capture_rollback_resets_file_position(tmp_path: Path) -> None:
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

    with capture_path.open("wb+") as capture_file:
        server._capture_file = capture_file
        capture_file.write(b"first")
        capture_file.flush()
        server._rollback_capture_payload(0)
        capture_file.write(b"second")
        capture_file.flush()

    assert capture_path.read_bytes() == b"second"


def test_stop_surfaces_capture_error(monkeypatch, tmp_path: Path) -> None:
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
        capture_path=tmp_path / "capture.bin",
    )

    server = SensorServer(config)
    server._capture_error = OSError("disk full")

    with pytest.raises(RuntimeError, match="capture"):
        server.stop()


def test_capture_file_matches_client_bytes_for_short_stream(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.bin"
    config = MockConfig(
        host="127.0.0.1",
        port=0,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1,
        mode="rate-controlled",
        ring_buffer_capacity=16,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=capture_path,
    )

    server = SensorServer(config)

    try:
        server.start()
        records = read_records(server.host, server.port, count=1, timeout_s=2.0)
    finally:
        server.stop()

    capture_bytes = capture_path.read_bytes()
    expected_bytes = b"".join(encode_record(record) for record in records)

    assert capture_bytes == expected_bytes


def test_start_cleans_up_listener_when_capture_open_fails(monkeypatch) -> None:
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
        capture_path=Path("capture.bin"),
    )

    server = SensorServer(config)
    close_calls: list[bool] = []

    class FakeListener:
        def setsockopt(self, *_args: object) -> None:
            pass

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 12345)

        def settimeout(self, _timeout: float) -> None:
            pass

        def listen(self, _backlog: int) -> None:
            pass

        def bind(self, _address: tuple[str, int]) -> None:
            pass

        def close(self) -> None:
            close_calls.append(True)

    class FakeSocketModule:
        AF_INET = socket.AF_INET
        SOCK_STREAM = socket.SOCK_STREAM
        SOL_SOCKET = socket.SOL_SOCKET
        SO_REUSEADDR = socket.SO_REUSEADDR

        def socket(self, *_args: object, **_kwargs: object) -> FakeListener:
            return FakeListener()

    monkeypatch.setattr("kc_sensor_mock.server.socket", FakeSocketModule())
    monkeypatch.setattr(
        "pathlib.Path.open",
        lambda self, mode: (_ for _ in ()).throw(OSError("cannot open capture")),
    )

    with pytest.raises(OSError, match="cannot open capture"):
        server.start()

    assert close_calls == [True]
