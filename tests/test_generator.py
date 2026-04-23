from __future__ import annotations

from dataclasses import replace

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, SensorRecord, encode_record
from kc_sensor_mock import generator as generator_module
from kc_sensor_mock.generator import RecordGenerator
from kc_sensor_mock.sample_data import SAMPLE_VALUES


def config() -> MockConfig:
    return MockConfig(
        bind_host="127.0.0.1",
        bind_port=9000,
        consumer_host=None,
        consumer_port=None,
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
    encoded = encode_record(record)

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
    assert record.values == SAMPLE_VALUES
    assert len(encoded) == 632


def test_sequence_wraps_to_zero_after_uint32_max(monkeypatch) -> None:
    monkeypatch.setattr(generator_module, "epoch_us_now", lambda: 1_778_000_000_000_000)

    generator = RecordGenerator(replace(config(), initial_sequence_number=2**32 - 1))
    first = generator.next_record(dropped_records_total=0)
    second = generator.next_record(dropped_records_total=0)

    assert first.sequence_number == 2**32 - 1
    assert second.sequence_number == 0
    assert encode_record(first)
    assert encode_record(second)


def test_dropped_records_total_wraps_to_uint32(monkeypatch) -> None:
    monkeypatch.setattr(generator_module, "epoch_us_now", lambda: 1_778_000_000_000_000)

    record = RecordGenerator(config()).next_record(dropped_records_total=2**32)

    assert record.dropped_records_total == 0
    assert encode_record(record)


def test_epoch_us_now_uses_time_ns(monkeypatch) -> None:
    class FakeTime:
        @staticmethod
        def time_ns() -> int:
            return 1_234_567_890_123_456_789

    monkeypatch.setattr(generator_module, "time", FakeTime, raising=False)

    assert generator_module.epoch_us_now() == 1_234_567_890_123_456


def test_initial_sequence_number_does_not_affect_timestamps(monkeypatch) -> None:
    timestamps = iter([100, 100])
    monkeypatch.setattr(generator_module, "epoch_us_now", lambda: next(timestamps))

    generator = RecordGenerator(replace(config(), initial_sequence_number=2**32 - 1))
    first = generator.next_record(dropped_records_total=0)
    second = generator.next_record(dropped_records_total=0)

    assert first.sensor_timestamp_us == 100
    assert second.sensor_timestamp_us == 101
    assert first.gps_timestamp_us == 100
    assert second.gps_timestamp_us == 101


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
