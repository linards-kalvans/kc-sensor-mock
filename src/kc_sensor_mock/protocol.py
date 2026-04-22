from __future__ import annotations

import struct
from dataclasses import dataclass, replace

SENSOR_VALUES_COUNT = 296
MEASUREMENT_TYPE_SPECTRA = 1
MEASUREMENT_TYPE_BACKGROUND_SPECTRA = 2
VALID_MEASUREMENT_TYPES = {
    MEASUREMENT_TYPE_SPECTRA,
    MEASUREMENT_TYPE_BACKGROUND_SPECTRA,
}

FORMAT = "<HHIIQQiii296H"
RECORD_SIZE = struct.calcsize(FORMAT)


@dataclass(frozen=True)
class SensorRecord:
    device_id: int
    measurement_type: int
    sequence_number: int
    dropped_records_total: int
    sensor_timestamp_us: int
    gps_timestamp_us: int
    gps_latitude_e7: int
    gps_longitude_e7: int
    gps_altitude_mm: int
    values: tuple[int, ...]

    def replace(self, **changes: object) -> SensorRecord:
        return replace(self, **changes)


def scale_latitude_e7(value: float) -> int:
    return round(value * 10_000_000)


def scale_longitude_e7(value: float) -> int:
    return round(value * 10_000_000)


def scale_altitude_mm(value: float) -> int:
    return round(value * 1_000)


def validate_record(record: SensorRecord) -> None:
    if record.measurement_type not in VALID_MEASUREMENT_TYPES:
        raise ValueError(
            f"measurement_type must be one of {sorted(VALID_MEASUREMENT_TYPES)}"
        )

    if len(record.values) != SENSOR_VALUES_COUNT:
        raise ValueError(f"values must contain exactly {SENSOR_VALUES_COUNT} items")

    for value in record.values:
        if not 0 <= value <= 65_535:
            raise ValueError("values must contain uint16 items")


def encode_record(record: SensorRecord) -> bytes:
    validate_record(record)
    return struct.pack(
        FORMAT,
        record.device_id,
        record.measurement_type,
        record.sequence_number,
        record.dropped_records_total,
        record.sensor_timestamp_us,
        record.gps_timestamp_us,
        record.gps_latitude_e7,
        record.gps_longitude_e7,
        record.gps_altitude_mm,
        *record.values,
    )


def decode_record(payload: bytes) -> SensorRecord:
    if len(payload) != RECORD_SIZE:
        raise ValueError(f"record payload must be exactly {RECORD_SIZE} bytes")

    fields = struct.unpack(FORMAT, payload)
    record = SensorRecord(
        device_id=fields[0],
        measurement_type=fields[1],
        sequence_number=fields[2],
        dropped_records_total=fields[3],
        sensor_timestamp_us=fields[4],
        gps_timestamp_us=fields[5],
        gps_latitude_e7=fields[6],
        gps_longitude_e7=fields[7],
        gps_altitude_mm=fields[8],
        values=tuple(fields[9:]),
    )
    validate_record(record)
    return record
