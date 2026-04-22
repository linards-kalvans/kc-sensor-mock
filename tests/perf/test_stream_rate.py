from __future__ import annotations

from time import perf_counter

import pytest

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, RECORD_SIZE
from kc_sensor_mock.server import SensorServer


@pytest.mark.perf
def test_stream_rate() -> None:
    count = 1_000
    config = MockConfig(
        host="127.0.0.1",
        port=0,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1_000,
        mode="rate-controlled",
        ring_buffer_capacity=2_048,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )

    server = SensorServer(config)

    try:
        server.start()
        started = perf_counter()
        records = read_records(
            server.host,
            server.port,
            count=count,
            timeout_s=10.0,
        )
        elapsed_s = perf_counter() - started
    finally:
        server.stop()

    assert len(records) == count

    records_per_second = count / elapsed_s
    bytes_per_second = (count * RECORD_SIZE) / elapsed_s
    print(
        f"read {count} records in {elapsed_s:.3f}s "
        f"({records_per_second:.1f} records/s, {bytes_per_second:.1f} bytes/s)"
    )
