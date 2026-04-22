from pathlib import Path

import pytest

from kc_sensor_mock.config import MockConfig, load_config


def _write_config(tmp_path: Path, body: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(body.strip(), encoding="utf-8")
    return config_path


def _base_config_body(**overrides: object) -> str:
    values: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 9000,
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

    lines = []
    for key, value in values.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        elif isinstance(value, Path):
            lines.append(f'{key} = "{value.as_posix()}"')
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        elif value is None:
            lines.append(f"{key} = null")
        else:
            lines.append(f"{key} = {value}")
    return "\n".join(lines)


def test_load_config_from_toml(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _base_config_body())

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
    config_path = _write_config(tmp_path, _base_config_body(capture_path="capture.bin"))

    config = load_config(config_path)

    assert config.capture_path == config_path.parent / "capture.bin"


def test_absolute_capture_path_from_toml_stays_absolute(tmp_path: Path) -> None:
    absolute_path = tmp_path / "capture.bin"
    config_path = _write_config(
        tmp_path,
        _base_config_body(capture_path=absolute_path.as_posix()),
    )

    config = load_config(config_path)

    assert config.capture_path == absolute_path


def test_cli_overrides_replace_config_values(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _base_config_body())

    config = load_config(config_path, overrides={"port": 9100, "mode": "burst"})

    assert config.port == 9100
    assert config.mode == "burst"


def test_cli_capture_path_override_stays_relative(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _base_config_body(capture_path="capture.bin"))

    config = load_config(config_path, overrides={"capture_path": Path("override.bin")})

    assert config.capture_path == Path("override.bin")


def test_cli_empty_string_capture_path_override_disables_toml_value(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _base_config_body(capture_path="capture.bin"))

    config = load_config(config_path, overrides={"capture_path": ""})

    assert config.capture_path is None


def test_cli_none_capture_path_override_is_ignored(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _base_config_body(capture_path="capture.bin"))

    config = load_config(config_path, overrides={"capture_path": None})

    assert config.capture_path == config_path.parent / "capture.bin"


@pytest.mark.parametrize(
    "_field, overrides, expected_message",
    [
        ("mode", None, "mode"),
        ("measurement_type", None, "measurement_type"),
        ("port", None, "port"),
        ("rate_hz", None, "rate_hz"),
        ("ring_buffer_capacity", None, "ring_buffer_capacity"),
        ("port", {"port": 65536}, "port"),
    ],
)
def test_load_config_rejects_invalid_boundary_values(
    tmp_path: Path,
    _field: str,
    overrides: dict[str, object] | None,
    expected_message: str,
) -> None:
    body_map = {
        "mode": _base_config_body(mode="invalid"),
        "measurement_type": _base_config_body(measurement_type=99),
        "port": _base_config_body(port=0),
        "rate_hz": _base_config_body(rate_hz=0),
        "ring_buffer_capacity": _base_config_body(ring_buffer_capacity=0),
    }
    config_path = _write_config(tmp_path, body_map[_field])

    with pytest.raises(ValueError, match=expected_message):
        load_config(config_path, overrides=overrides)


@pytest.mark.parametrize(
    "field, value, expected_message",
    [
        ("port", 9000.9, "port"),
        ("port", True, "port"),
        ("device_id", 1.2, "device_id"),
        ("device_id", False, "device_id"),
        ("measurement_type", 1.1, "measurement_type"),
        ("measurement_type", True, "measurement_type"),
        ("rate_hz", 1000.5, "rate_hz"),
        ("rate_hz", True, "rate_hz"),
        ("ring_buffer_capacity", 4096.3, "ring_buffer_capacity"),
        ("ring_buffer_capacity", True, "ring_buffer_capacity"),
        ("initial_sequence_number", 0.7, "initial_sequence_number"),
        ("initial_sequence_number", False, "initial_sequence_number"),
    ],
)
def test_load_config_rejects_non_integer_values(
    tmp_path: Path,
    field: str,
    value: object,
    expected_message: str,
) -> None:
    config_path = _write_config(tmp_path, _base_config_body(**{field: value}))

    with pytest.raises(ValueError, match=expected_message):
        load_config(config_path)


@pytest.mark.parametrize(
    "field, value, expected_message",
    [
        ("device_id", 65_536, "device_id"),
        ("initial_sequence_number", 2**32, "initial_sequence_number"),
        ("gps_latitude", 91.0, "gps_latitude"),
        ("gps_latitude", -91.0, "gps_latitude"),
        ("gps_longitude", 181.0, "gps_longitude"),
        ("gps_longitude", -181.0, "gps_longitude"),
        ("gps_altitude_m", 3_000_000.0, "gps_altitude_m"),
    ],
)
def test_load_config_rejects_out_of_range_values(
    tmp_path: Path,
    field: str,
    value: object,
    expected_message: str,
) -> None:
    config_path = _write_config(tmp_path, _base_config_body(**{field: value}))

    with pytest.raises(ValueError, match=expected_message):
        load_config(config_path)


def test_gps_altitude_that_scales_to_int32_limit_is_accepted(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _base_config_body(gps_altitude_m=2_147_483.647))

    config = load_config(config_path)

    assert config.gps_altitude_m == pytest.approx(2_147_483.647)
