import struct

import pytest

from kc_sensor_mock.protocol import (
    FORMAT,
    MEASUREMENT_TYPE_BACKGROUND_SPECTRA,
    MEASUREMENT_TYPE_SPECTRA,
    RECORD_SIZE,
    SENSOR_VALUES_COUNT,
    SensorRecord,
    decode_record,
    encode_record,
    scale_altitude_mm,
    scale_latitude_e7,
    scale_longitude_e7,
)


def make_record() -> SensorRecord:
    return SensorRecord(
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        sequence_number=7,
        dropped_records_total=2,
        sensor_timestamp_us=1_778_000_000_000_001,
        gps_timestamp_us=1_778_000_000_000_002,
        gps_latitude_e7=566_718_316,
        gps_longitude_e7=242_391_946,
        gps_altitude_mm=35_000,
        values=tuple(range(SENSOR_VALUES_COUNT)),
    )


def test_record_size_is_632_bytes():
    assert FORMAT == "<HHIIQQiii296H"
    assert SENSOR_VALUES_COUNT == 296
    assert RECORD_SIZE == 632
    assert struct.calcsize(FORMAT) == RECORD_SIZE


def test_pack_unpack_roundtrip_preserves_fields():
    record = make_record()

    packed = encode_record(record)
    unpacked = decode_record(packed)

    assert len(packed) == RECORD_SIZE
    assert unpacked == record


def test_rejects_invalid_measurement_type():
    record = make_record()
    invalid = record.replace(measurement_type=99)

    with pytest.raises(ValueError, match="measurement_type"):
        encode_record(invalid)


def test_rejects_wrong_values_count():
    record = make_record().replace(values=(1, 2, 3))

    with pytest.raises(ValueError, match="296"):
        encode_record(record)


def test_rejects_out_of_range_uint16_value():
    record = make_record().replace(values=tuple([0] * 295 + [65_536]))

    with pytest.raises(ValueError, match="uint16"):
        encode_record(record)


def test_rejects_partial_record_decode():
    with pytest.raises(ValueError, match="632"):
        decode_record(b"\x00" * 631)


def test_scaling_helpers_are_deterministic():
    assert scale_latitude_e7(56.6718316) == 566_718_316
    assert scale_longitude_e7(24.2391946) == 242_391_946
    assert scale_altitude_mm(35.0) == 35_000


def test_background_measurement_type_is_supported():
    record = make_record().replace(measurement_type=MEASUREMENT_TYPE_BACKGROUND_SPECTRA)

    assert decode_record(encode_record(record)).measurement_type == 2
