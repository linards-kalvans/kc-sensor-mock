from __future__ import annotations

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, SensorRecord
from kc_sensor_mock import generator as generator_module
from kc_sensor_mock.generator import RecordGenerator


def config() -> MockConfig:
    return MockConfig(
        host="127.0.0.1",
        port=9000,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="rate-controlled",
        ring_buffer_capacity=4096,
        initial_sequence_number=10,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )


def test_next_record_uses_config_and_sample_values(monkeypatch) -> None:
    monkeypatch.setattr(generator_module, "epoch_us_now", lambda: 1_778_000_000_000_000)

    record = RecordGenerator(config()).next_record(dropped_records_total=3)

    assert isinstance(record, SensorRecord)
    assert record.device_id == 1
    assert record.measurement_type == MEASUREMENT_TYPE_SPECTRA
    assert record.sequence_number == 10
    assert record.dropped_records_total == 3
    assert record.sensor_timestamp_us == 1_778_000_000_000_000
    assert record.gps_timestamp_us == 1_778_000_000_000_000
    assert record.gps_latitude_e7 == 566_718_316
    assert record.gps_longitude_e7 == 242_391_946
    assert record.gps_altitude_mm == 35_000
    assert len(record.values) == 296


def test_sequence_and_timestamps_increase(monkeypatch) -> None:
    timestamps = iter([1_778_000_000_000_000, 1_778_000_000_000_000])
    monkeypatch.setattr(generator_module, "epoch_us_now", lambda: next(timestamps))

    generator = RecordGenerator(config())
    first = generator.next_record(dropped_records_total=0)
    second = generator.next_record(dropped_records_total=0)

    assert second.sequence_number == first.sequence_number + 1
    assert first.sensor_timestamp_us < second.sensor_timestamp_us
    assert first.gps_timestamp_us < second.gps_timestamp_us
    assert second.sensor_timestamp_us == 1_778_000_000_000_001
    assert second.gps_timestamp_us == 1_778_000_000_000_001
