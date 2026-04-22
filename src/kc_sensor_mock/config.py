from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kc_sensor_mock.protocol import VALID_MEASUREMENT_TYPES

VALID_MODES = {"rate-controlled", "burst"}


@dataclass(frozen=True)
class MockConfig:
    host: str
    port: int
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


def _validate_mode(value: str) -> str:
    if value not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
    return value


def _validate_measurement_type(value: int) -> int:
    if value not in VALID_MEASUREMENT_TYPES:
        raise ValueError(
            f"measurement_type must be one of {sorted(VALID_MEASUREMENT_TYPES)}"
        )
    return value


def _validate_positive_int(name: str, value: int) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _validate_port(value: int) -> int:
    if value <= 0 or value > 65_535:
        raise ValueError("port must be positive and <= 65535")
    return value


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

    host = str(data["host"])
    port = _validate_port(int(data["port"]))
    device_id = int(data["device_id"])
    measurement_type = _validate_measurement_type(int(data["measurement_type"]))
    rate_hz = _validate_positive_int("rate_hz", int(data["rate_hz"]))
    mode = _validate_mode(str(data["mode"]))
    ring_buffer_capacity = _validate_positive_int(
        "ring_buffer_capacity", int(data["ring_buffer_capacity"])
    )
    initial_sequence_number = int(data["initial_sequence_number"])
    gps_latitude = float(data["gps_latitude"])
    gps_longitude = float(data["gps_longitude"])
    gps_altitude_m = float(data["gps_altitude_m"])

    capture_path = _resolve_capture_path(
        override_capture_path if override_capture_path is not None else data.get("capture_path"),
        path.parent,
        from_override=override_capture_path is not None,
    )

    return MockConfig(
        host=host,
        port=port,
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
    )
