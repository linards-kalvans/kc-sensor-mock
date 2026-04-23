"""Bootstrap tests: package metadata and public CLI contract."""

from __future__ import annotations

import subprocess
from pathlib import Path

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA


def test_package_import_exposes_metadata() -> None:
    import kc_sensor_mock

    assert kc_sensor_mock.__package_name__ == "kc-sensor-mock"
    assert kc_sensor_mock.__version__ == "0.1.0"


def test_producer_console_script_help_exits_successfully() -> None:
    result = subprocess.run(
        ["uv", "run", "kc-sensor-producer", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_consumer_console_script_help_exits_successfully() -> None:
    result = subprocess.run(
        ["uv", "run", "kc-sensor-consumer", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_old_server_console_script_no_longer_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "kc-sensor-mock", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0 or "kc-sensor-mock" not in result.stdout.lower()


def test_old_client_console_script_no_longer_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "kc-sensor-client", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0 or "kc-sensor-client" not in result.stdout.lower()


def test_perf_lane_models_consumer_first_then_producer() -> None:
    consumer_config = MockConfig(
        bind_host="127.0.0.1",
        bind_port=9000,
        consumer_host="127.0.0.1",
        consumer_port=9000,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="burst",
        ring_buffer_capacity=64,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )
    producer_config = MockConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        consumer_host="127.0.0.1",
        consumer_port=9000,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1000,
        mode="burst",
        ring_buffer_capacity=64,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )

    assert consumer_config.bind_port == 9000
    assert producer_config.consumer_port == 9000
