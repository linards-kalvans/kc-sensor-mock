"""Tests for config: producer/consumer endpoint fields."""

from __future__ import annotations

from pathlib import Path

import pytest

from kc_sensor_mock.config import MockConfig, load_config


def _write_config(tmp_path: Path, **overrides: object) -> Path:
    values: dict[str, object] = {
        "bind_host": "127.0.0.1",
        "bind_port": 9000,
        "consumer_host": "127.0.0.1",
        "consumer_port": 8080,
        "device_id": 1,
        "measurement_type": 1,
        "rate_hz": 1000,
        "mode": "rate-controlled",
        "ring_buffer_capacity": 4096,
        "initial_sequence_number": 0,
        "gps_latitude": 56.6718316,
        "gps_longitude": 24.2391946,
        "gps_altitude_m": 35.0,
        "capture_path": "",
    }
    values.update(overrides)

    lines: list[str] = []
    for key, value in values.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {value}")

    config_path = tmp_path / "config.toml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config_path


# --- AC-9: Config supports consumer_host, consumer_port, bind_host, bind_port ---

def test_load_config_accepts_consumer_endpoint_fields(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path,
            consumer_host="10.0.0.5",
            consumer_port=8080,
            bind_host="0.0.0.0",
            bind_port=9090,
        )
    )

    assert config.consumer_host == "10.0.0.5"
    assert config.consumer_port == 8080
    assert config.bind_host == "0.0.0.0"
    assert config.bind_port == 9090


def test_load_config_accepts_bind_endpoint_fields_only(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'bind_host = "0.0.0.0"',
                "bind_port = 5555",
                "device_id = 2",
                "measurement_type = 1",
                "rate_hz = 500",
                'mode = "burst"',
                "ring_buffer_capacity = 2048",
                "initial_sequence_number = 100",
                "gps_latitude = 56.6718316",
                "gps_longitude = 24.2391946",
                "gps_altitude_m = 35.0",
                'capture_path = ""',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.bind_host == "0.0.0.0"
    assert config.bind_port == 5555
    assert config.consumer_host is None
    assert config.consumer_port is None


def test_load_config_accepts_producer_endpoint_fields_only(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'consumer_host = "192.168.1.10"',
                "consumer_port = 7777",
                "device_id = 3",
                "measurement_type = 1",
                "rate_hz = 200",
                'mode = "rate-controlled"',
                "ring_buffer_capacity = 1024",
                "initial_sequence_number = 0",
                "gps_latitude = 56.6718316",
                "gps_longitude = 24.2391946",
                "gps_altitude_m = 35.0",
                'capture_path = ""',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.consumer_host == "192.168.1.10"
    assert config.consumer_port == 7777
    assert config.bind_host is None
    assert config.bind_port is None


def test_cli_overrides_consumer_endpoint_fields(tmp_path: Path) -> None:
    config = load_config(
        _write_config(tmp_path, consumer_host="10.0.0.5", consumer_port=8080),
        overrides={"consumer_host": "10.0.0.99", "bind_port": 1234},
    )

    assert config.consumer_host == "10.0.0.99"
    assert config.bind_port == 1234


@pytest.mark.parametrize(
    "field, value, expected_message",
    [
        ("bind_port", 0, "bind_port"),
        ("consumer_port", 0, "consumer_port"),
        ("rate_hz", 0, "rate_hz"),
        ("ring_buffer_capacity", 0, "ring_buffer_capacity"),
        ("bind_port", 65536, "bind_port"),
        ("consumer_port", 65536, "consumer_port"),
    ],
)
def test_load_config_rejects_invalid_boundary_values(
    tmp_path: Path,
    field: str,
    value: object,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        load_config(_write_config(tmp_path, **{field: value}))


def test_capture_path_from_toml_is_relative_to_config_file(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, capture_path="capture.bin"))
    assert config.capture_path == tmp_path / "capture.bin"


def test_gps_altitude_that_scales_to_int32_limit_is_accepted(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, gps_altitude_m=2147483.647))
    assert config.gps_altitude_m == pytest.approx(2_147_483.647)


def test_load_config_rejects_non_integer_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bind_port"):
        load_config(_write_config(tmp_path, bind_port=9000.9))


def test_load_config_rejects_out_of_range_latitude(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="gps_latitude"):
        load_config(_write_config(tmp_path, gps_latitude=91.0))


# --- Old host/port fields should be rejected ---

def test_load_config_rejects_old_host_field(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(config_path.read_text(encoding="utf-8") + 'host = "127.0.0.1"\n', encoding="utf-8")

    with pytest.raises((KeyError, ValueError)):
        load_config(config_path)


def test_load_config_rejects_old_port_field(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(config_path.read_text(encoding="utf-8") + "port = 9000\n", encoding="utf-8")

    with pytest.raises((KeyError, ValueError)):
        load_config(config_path)
