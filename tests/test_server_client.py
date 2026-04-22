from __future__ import annotations

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA
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
