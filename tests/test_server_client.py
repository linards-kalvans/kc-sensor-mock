from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, SensorRecord
from kc_sensor_mock.server import SensorServer


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
        SensorRecord(
            device_id=1,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            sequence_number=10,
            dropped_records_total=0,
            sensor_timestamp_us=100,
            gps_timestamp_us=100,
            gps_latitude_e7=1,
            gps_longitude_e7=2,
            gps_altitude_mm=3,
            values=tuple(range(296)),
        ),
        SensorRecord(
            device_id=1,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            sequence_number=10,
            dropped_records_total=0,
            sensor_timestamp_us=101,
            gps_timestamp_us=101,
            gps_latitude_e7=1,
            gps_longitude_e7=2,
            gps_altitude_mm=3,
            values=tuple(range(296)),
        ),
    ]

    with pytest.raises(ValueError, match="sequence"):
        validate_record_stream(records)


def test_validate_record_stream_rejects_non_increasing_timestamps() -> None:
    from kc_sensor_mock.client import validate_record_stream

    records = [
        SensorRecord(
            device_id=1,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            sequence_number=10,
            dropped_records_total=0,
            sensor_timestamp_us=100,
            gps_timestamp_us=100,
            gps_latitude_e7=1,
            gps_longitude_e7=2,
            gps_altitude_mm=3,
            values=tuple(range(296)),
        ),
        SensorRecord(
            device_id=1,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            sequence_number=11,
            dropped_records_total=0,
            sensor_timestamp_us=100,
            gps_timestamp_us=99,
            gps_latitude_e7=1,
            gps_longitude_e7=2,
            gps_altitude_mm=3,
            values=tuple(range(296)),
        ),
    ]

    with pytest.raises(ValueError, match="timestamp"):
        validate_record_stream(records)


def test_validate_record_stream_rejects_wrong_values_length() -> None:
    from kc_sensor_mock.client import validate_record_stream

    records = [
        SensorRecord(
            device_id=1,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            sequence_number=10,
            dropped_records_total=0,
            sensor_timestamp_us=100,
            gps_timestamp_us=100,
            gps_latitude_e7=1,
            gps_longitude_e7=2,
            gps_altitude_mm=3,
            values=tuple(range(295)),
        )
    ]

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

    failing_capture = Mock()
    failing_capture.write.side_effect = OSError("disk full")
    failing_capture.flush.return_value = None
    monkeypatch.setattr(server, "_capture_file", failing_capture)
    monkeypatch.setattr(server, "_stop_event", Mock(set=Mock()))

    server._write_capture_payload(b"abc")

    assert server._stop_event.set.called
    assert server._capture_error is not None
