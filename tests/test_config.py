from pathlib import Path

from kc_sensor_mock.config import MockConfig, load_config


def test_load_config_from_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
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
""".strip(),
        encoding="utf-8",
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


def test_cli_overrides_replace_config_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
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
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path, overrides={"port": 9100, "mode": "burst"})

    assert config.port == 9100
    assert config.mode == "burst"
