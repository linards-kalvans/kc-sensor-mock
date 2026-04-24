from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kc_sensor_mock.protocol import VALID_MEASUREMENT_TYPES, scale_altitude_mm

VALID_MODES = {"rate-controlled", "burst"}
VALID_PARQUET_BATCH_MODES = {"volume", "time"}
PARQUET_DEFAULTS = {
    "parquet_max_records_per_file": 1000,
    "parquet_flush_interval_seconds": 1.0,
    "parquet_queue_capacity": 256,
}


@dataclass(frozen=True)
class MockConfig:
    bind_host: str | None
    bind_port: int | None
    consumer_host: str | None
    consumer_port: int | None
    device_id: int
    measurement_type: int
    rate_hz: int
    mode: str
    ring_buffer_capacity: int
    initial_sequence_number: int
    gps_latitude: float
    gps_longitude: float
    gps_altitude_m: float
    capture_path: Path | None
    parquet_enabled: bool = False
    parquet_output_dir: Path | None = None
    parquet_batch_mode: str | None = None
    parquet_max_records_per_file: int = PARQUET_DEFAULTS["parquet_max_records_per_file"]
    parquet_flush_interval_seconds: float = PARQUET_DEFAULTS["parquet_flush_interval_seconds"]
    parquet_queue_capacity: int = PARQUET_DEFAULTS["parquet_queue_capacity"]


def _validate_mode(value: str) -> str:
    if value not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
    return value


def _require_exact_int(name: str, value: object) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an int")
    return value


def _validate_measurement_type(value: object) -> int:
    int_value = _require_exact_int("measurement_type", value)
    if int_value not in VALID_MEASUREMENT_TYPES:
        raise ValueError(
            f"measurement_type must be one of {sorted(VALID_MEASUREMENT_TYPES)}"
        )
    return int_value


def _validate_uint16(name: str, value: object) -> int:
    int_value = _require_exact_int(name, value)
    if not 0 <= int_value <= 65_535:
        raise ValueError(f"{name} must be between 0 and 65535")
    return int_value


def _validate_uint32(name: str, value: object) -> int:
    int_value = _require_exact_int(name, value)
    if not 0 <= int_value <= 2**32 - 1:
        raise ValueError(f"{name} must be between 0 and 4294967295")
    return int_value


def _validate_positive_int(name: str, value: object) -> int:
    int_value = _require_exact_int(name, value)
    if int_value <= 0:
        raise ValueError(f"{name} must be positive")
    return int_value


def _validate_port(value: object, name: str = "port") -> int:
    int_value = _validate_positive_int(name, value)
    if int_value > 65_535:
        raise ValueError(f"{name} must be positive and <= 65535")
    return int_value


def _validate_numeric(name: str, value: object) -> float:
    if type(value) is bool or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _validate_latitude(value: object) -> float:
    numeric = _validate_numeric("gps_latitude", value)
    if not -90.0 <= numeric <= 90.0:
        raise ValueError("gps_latitude must be between -90 and 90")
    return numeric


def _validate_longitude(value: object) -> float:
    numeric = _validate_numeric("gps_longitude", value)
    if not -180.0 <= numeric <= 180.0:
        raise ValueError("gps_longitude must be between -180 and 180")
    return numeric


def _validate_altitude(value: object) -> float:
    numeric = _validate_numeric("gps_altitude_m", value)
    scaled = scale_altitude_mm(numeric)
    if not -(2**31) <= scaled <= 2**31 - 1:
        raise ValueError("gps_altitude_m must fit in int32 when scaled to millimeters")
    return numeric


def _validate_device_id(value: object) -> int:
    return _validate_uint16("device_id", value)


def _validate_initial_sequence_number(value: object) -> int:
    return _validate_uint32("initial_sequence_number", value)


def _validate_rate_hz(value: object) -> int:
    return _validate_positive_int("rate_hz", value)


def _validate_ring_buffer_capacity(value: object) -> int:
    return _validate_positive_int("ring_buffer_capacity", value)


def _resolve_capture_path(
    raw_value: object,
    config_dir: Path,
    *,
    from_override: bool,
) -> Path | None:
    if raw_value in ("", None):
        return None

    path = Path(raw_value)
    if from_override or path.is_absolute():
        return path

    return config_dir / path


def load_config(path: Path, overrides: dict[str, Any] | None = None) -> MockConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    override_capture_path = None
    if overrides:
        override_capture_path = overrides.get("capture_path")
        data.update(
            {
                key: value
                for key, value in overrides.items()
                if key != "capture_path" and value is not None
            }
        )

    # Reject old host/port field names
    for old_key in ("host", "port"):
        if old_key in data:
            raise KeyError(f"{old_key} is no longer a valid config field; use bind_host/bind_port or consumer_host/consumer_port")

    bind_host = str(data.get("bind_host", "")) or None
    bind_port = _validate_port(data["bind_port"], "bind_port") if "bind_port" in data else None
    consumer_host = str(data.get("consumer_host", "")) or None
    consumer_port = _validate_port(data["consumer_port"], "consumer_port") if "consumer_port" in data else None
    device_id = _validate_device_id(data["device_id"])
    measurement_type = _validate_measurement_type(data["measurement_type"])
    rate_hz = _validate_rate_hz(data["rate_hz"])
    mode = _validate_mode(str(data["mode"]))
    ring_buffer_capacity = _validate_ring_buffer_capacity(data["ring_buffer_capacity"])
    initial_sequence_number = _validate_initial_sequence_number(
        data["initial_sequence_number"]
    )
    gps_latitude = _validate_latitude(data["gps_latitude"])
    gps_longitude = _validate_longitude(data["gps_longitude"])
    gps_altitude_m = _validate_altitude(data["gps_altitude_m"])

    capture_path = _resolve_capture_path(
        override_capture_path if override_capture_path is not None else data.get("capture_path"),
        path.parent,
        from_override=override_capture_path is not None,
    )

    # Parquet fields
    parquet_enabled = bool(data.get("parquet_enabled", False))
    parquet_output_dir_raw = data.get("parquet_output_dir")
    parquet_output_dir_set = "parquet_output_dir" in data
    parquet_output_dir = Path(parquet_output_dir_raw) if parquet_output_dir_raw else None
    parquet_batch_mode = data.get("parquet_batch_mode")
    parquet_max_records_per_file = int(data.get("parquet_max_records_per_file", PARQUET_DEFAULTS["parquet_max_records_per_file"]))
    parquet_flush_interval_seconds = float(data.get("parquet_flush_interval_seconds", PARQUET_DEFAULTS["parquet_flush_interval_seconds"]))
    parquet_queue_capacity = int(data.get("parquet_queue_capacity", PARQUET_DEFAULTS["parquet_queue_capacity"]))

    # Validation: batch_mode must always be valid when present
    if parquet_batch_mode is not None and parquet_batch_mode not in VALID_PARQUET_BATCH_MODES:
        raise ValueError(f"parquet_batch_mode must be one of {sorted(VALID_PARQUET_BATCH_MODES)}")

    # Validation when enabled
    if parquet_enabled:
        if parquet_output_dir is None:
            raise ValueError("parquet_enabled requires parquet_output_dir")
        if parquet_batch_mode is None:
            parquet_batch_mode = "volume"
        if parquet_batch_mode == "volume" and parquet_max_records_per_file <= 0:
            raise ValueError("parquet_max_records_per_file must be positive for volume mode")
        if parquet_batch_mode == "time" and parquet_flush_interval_seconds <= 0:
            raise ValueError("parquet_flush_interval_seconds must be positive for time mode")

    return MockConfig(
        bind_host=bind_host,
        bind_port=bind_port,
        consumer_host=consumer_host,
        consumer_port=consumer_port,
        device_id=device_id,
        measurement_type=measurement_type,
        rate_hz=rate_hz,
        mode=mode,
        ring_buffer_capacity=ring_buffer_capacity,
        initial_sequence_number=initial_sequence_number,
        gps_latitude=gps_latitude,
        gps_longitude=gps_longitude,
        gps_altitude_m=gps_altitude_m,
        capture_path=capture_path,
        parquet_enabled=parquet_enabled,
        parquet_output_dir=parquet_output_dir,
        parquet_batch_mode=parquet_batch_mode,
        parquet_max_records_per_file=parquet_max_records_per_file,
        parquet_flush_interval_seconds=parquet_flush_interval_seconds,
        parquet_queue_capacity=parquet_queue_capacity,
    )
