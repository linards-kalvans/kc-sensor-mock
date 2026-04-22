from pathlib import Path

import pytest

from kc_sensor_mock.config import MockConfig, load_config


def _write_config(tmp_path: Path, body: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(body.strip(), encoding="utf-8")
    return config_path


def test_load_config_from_toml(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
    )

    config = load_config(config_path)

    assert config == MockConfig(
        host="127.0.0.1",
        port=9000,
        device_id=1,
        measurement_type=1,
        rate_hz=1000,
        mode="rate-controlled",
        ring_buffer_capacity=4096,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )


def test_capture_path_from_toml_is_relative_to_config_file(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = "capture.bin"
""",
    )

    config = load_config(config_path)

    assert config.capture_path == config_path.parent / "capture.bin"


def test_cli_overrides_replace_config_values(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
    )

    config = load_config(config_path, overrides={"port": 9100, "mode": "burst"})

    assert config.port == 9100
    assert config.mode == "burst"


def test_cli_capture_path_override_stays_relative(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = "capture.bin"
""",
    )

    config = load_config(config_path, overrides={"capture_path": Path("override.bin")})

    assert config.capture_path == Path("override.bin")


def test_cli_none_capture_path_override_is_ignored(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = "capture.bin"
""",
    )

    config = load_config(config_path, overrides={"capture_path": None})

    assert config.capture_path == config_path.parent / "capture.bin"


@pytest.mark.parametrize(
    "_field, body, overrides, expected_message",
    [
        (
            "mode",
            """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "invalid"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
            None,
            "mode",
        ),
        (
            "measurement_type",
            """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 99
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
            None,
            "measurement_type",
        ),
        (
            "port",
            """
host = "127.0.0.1"
port = 0
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
            None,
            "port",
        ),
        (
            "rate_hz",
            """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 0
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
            None,
            "rate_hz",
        ),
        (
            "ring_buffer_capacity",
            """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 0
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
            None,
            "ring_buffer_capacity",
        ),
        (
            "port",
            """
host = "127.0.0.1"
port = 9000
device_id = 1
measurement_type = 1
rate_hz = 1000
mode = "rate-controlled"
ring_buffer_capacity = 4096
initial_sequence_number = 0
gps_latitude = 56.6718316
gps_longitude = 24.2391946
gps_altitude_m = 35.0
capture_path = ""
""",
            {"port": 65536},
            "port",
        ),
    ],
)
def test_load_config_rejects_invalid_boundary_values(
    tmp_path: Path,
    _field: str,
    body: str,
    overrides: dict[str, object] | None,
    expected_message: str,
) -> None:
    config_path = _write_config(tmp_path, body)

    with pytest.raises(ValueError, match=expected_message):
        load_config(config_path, overrides=overrides)
