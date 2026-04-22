from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


def load_config(path: Path, overrides: dict[str, Any] | None = None) -> MockConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    if overrides:
        data.update({key: value for key, value in overrides.items() if value is not None})

    capture_path_value = data.get("capture_path") or None

    return MockConfig(
        host=str(data["host"]),
        port=int(data["port"]),
        device_id=int(data["device_id"]),
        measurement_type=int(data["measurement_type"]),
        rate_hz=int(data["rate_hz"]),
        mode=str(data["mode"]),
        ring_buffer_capacity=int(data["ring_buffer_capacity"]),
        initial_sequence_number=int(data["initial_sequence_number"]),
        gps_latitude=float(data["gps_latitude"]),
        gps_longitude=float(data["gps_longitude"]),
        gps_altitude_m=float(data["gps_altitude_m"]),
        capture_path=Path(capture_path_value) if capture_path_value else None,
    )
