from __future__ import annotations

from pathlib import Path

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, RECORD_SIZE, encode_record
from kc_sensor_mock.server import SensorServer


def test_capture_matches_streamed_records(tmp_path: Path) -> None:
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

    try:
        server.start()
        records = read_records(
            server.host,
            server.port,
            count=3,
            timeout_s=2.0,
        )
    finally:
        server.stop()

    assert capture_path.exists()

    captured = capture_path.read_bytes()
    expected = b"".join(encode_record(record) for record in records)

    assert len(captured) >= len(expected)
    assert len(captured) % RECORD_SIZE == 0
    assert captured[: len(expected)] == expected
