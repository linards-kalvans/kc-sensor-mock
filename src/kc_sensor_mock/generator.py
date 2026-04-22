from __future__ import annotations

from datetime import datetime, timezone

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import (
    SensorRecord,
    scale_altitude_mm,
    scale_latitude_e7,
    scale_longitude_e7,
)
from kc_sensor_mock.sample_data import SAMPLE_VALUES


def epoch_us_now() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000)


class RecordGenerator:
    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._next_sequence_number = config.initial_sequence_number
        self._last_timestamp_us = config.initial_sequence_number - 1

    def next_record(self, dropped_records_total: int) -> SensorRecord:
        current_timestamp_us = epoch_us_now()
        timestamp_us = max(current_timestamp_us, self._last_timestamp_us + 1)
        self._last_timestamp_us = timestamp_us

        record = SensorRecord(
            device_id=self._config.device_id,
            measurement_type=self._config.measurement_type,
            sequence_number=self._next_sequence_number,
            dropped_records_total=dropped_records_total,
            sensor_timestamp_us=timestamp_us,
            gps_timestamp_us=timestamp_us,
            gps_latitude_e7=scale_latitude_e7(self._config.gps_latitude),
            gps_longitude_e7=scale_longitude_e7(self._config.gps_longitude),
            gps_altitude_mm=scale_altitude_mm(self._config.gps_altitude_m),
            values=tuple(SAMPLE_VALUES),
        )

        self._next_sequence_number += 1
        return record
