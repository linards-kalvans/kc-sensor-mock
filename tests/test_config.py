"""Tests for config: producer/consumer endpoint fields, parquet fields."""

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
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        else:
            lines.append(f"{key} = {value}")

    config_path = tmp_path / "config.toml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config_path


# ---------------------------------------------------------------------------
# Endpoint fields: AC-9
# ---------------------------------------------------------------------------


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
                'bind_host = "127.0.0.1"',
                "bind_port = 9000",
                "device_id = 1",
                "measurement_type = 1",
                "rate_hz = 1000",
                'mode = "rate-controlled"',
                "ring_buffer_capacity = 4096",
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
    assert config.bind_host == "127.0.0.1"
    assert config.bind_port == 9000
    assert config.consumer_host is None
    assert config.consumer_port is None


def test_load_config_accepts_producer_endpoint_fields_only(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'consumer_host = "127.0.0.1"',
                "consumer_port = 8080",
                "device_id = 1",
                "measurement_type = 1",
                "rate_hz = 1000",
                'mode = "rate-controlled"',
                "ring_buffer_capacity = 4096",
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
    assert config.consumer_host == "127.0.0.1"
    assert config.consumer_port == 8080
    assert config.bind_host is None
    assert config.bind_port is None


def test_cli_overrides_consumer_endpoint_fields(tmp_path: Path) -> None:
    config = load_config(
        _write_config(tmp_path, consumer_host="10.0.0.5", consumer_port=8080),
        overrides={"consumer_host": "10.0.0.99", "bind_port": 1234},
    )
    assert config.consumer_host == "10.0.0.99"
    assert config.bind_port == 1234


# ---------------------------------------------------------------------------
# Validation: boundary values, GPS ranges, old fields
# ---------------------------------------------------------------------------


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


def test_load_config_rejects_old_host_field(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + 'host = "127.0.0.1"\n',
        encoding="utf-8",
    )
    with pytest.raises((KeyError, ValueError)):
        load_config(config_path)


def test_load_config_rejects_old_port_field(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(config_path.read_text(encoding="utf-8") + "port = 9000\n", encoding="utf-8")
    with pytest.raises((KeyError, ValueError)):
        load_config(config_path)


# ---------------------------------------------------------------------------
# Parquet fields exist on MockConfig: AC-1
# ---------------------------------------------------------------------------


def test_mock_config_has_parquet_enabled_field() -> None:
    assert hasattr(MockConfig, "parquet_enabled")


def test_mock_config_has_parquet_output_dir_field() -> None:
    assert hasattr(MockConfig, "parquet_output_dir")


def test_mock_config_has_parquet_batch_mode_field() -> None:
    assert hasattr(MockConfig, "parquet_batch_mode")


def test_mock_config_has_parquet_max_records_per_file_field() -> None:
    assert hasattr(MockConfig, "parquet_max_records_per_file")


def test_mock_config_has_parquet_flush_interval_seconds_field() -> None:
    assert hasattr(MockConfig, "parquet_flush_interval_seconds")


def test_mock_config_has_parquet_queue_capacity_field() -> None:
    assert hasattr(MockConfig, "parquet_queue_capacity")


# ---------------------------------------------------------------------------
# Disabled config: defaults are unset/disabled
# ---------------------------------------------------------------------------


def test_load_config_defaults_parquet_enabled_to_false(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.parquet_enabled is False


def test_load_config_defaults_parquet_output_dir_to_none(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.parquet_output_dir is None


def test_load_config_defaults_parquet_batch_mode_to_none(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.parquet_batch_mode is None


def test_load_config_defaults_parquet_max_records_per_file(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.parquet_max_records_per_file == 1000


def test_load_config_defaults_parquet_flush_interval_seconds(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.parquet_flush_interval_seconds == pytest.approx(1.0)


def test_load_config_defaults_parquet_queue_capacity(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    assert config.parquet_queue_capacity == 256


# ---------------------------------------------------------------------------
# Enabled config: reads parquet fields, defaults batch_mode to volume
# ---------------------------------------------------------------------------


def test_load_config_reads_parquet_enabled_from_toml(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_enabled=True, parquet_output_dir="/tmp/parquet_out"))
    assert config.parquet_enabled is True


def test_load_config_reads_parquet_output_dir_from_toml(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_output_dir="/tmp/parquet_out"))
    assert config.parquet_output_dir == Path("/tmp/parquet_out")


def test_load_config_reads_parquet_batch_mode_from_toml(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_batch_mode="volume"))
    assert config.parquet_batch_mode == "volume"


def test_load_config_reads_parquet_max_records_per_file_from_toml(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_max_records_per_file=500))
    assert config.parquet_max_records_per_file == 500


def test_load_config_reads_parquet_flush_interval_seconds_from_toml(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_flush_interval_seconds=5.0))
    assert config.parquet_flush_interval_seconds == pytest.approx(5.0)


def test_load_config_reads_parquet_queue_capacity_from_toml(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_queue_capacity=128))
    assert config.parquet_queue_capacity == 128


def test_load_config_enabled_with_omitted_batch_mode_defaults_to_volume(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_enabled=True, parquet_output_dir="/tmp/parquet_out"))
    assert config.parquet_enabled is True
    assert config.parquet_batch_mode == "volume"


def test_load_config_enabled_with_explicit_batch_mode_time(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, parquet_enabled=True, parquet_output_dir="/tmp/parquet_out", parquet_batch_mode="time"))
    assert config.parquet_batch_mode == "time"


# ---------------------------------------------------------------------------
# Invalid combinations fail fast
# ---------------------------------------------------------------------------


def test_load_config_rejects_invalid_parquet_batch_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="parquet_batch_mode"):
        load_config(_write_config(tmp_path, parquet_batch_mode="invalid_mode"))


def test_load_config_enabled_without_output_dir_fails(tmp_path: Path) -> None:
    """Enabled export requires parquet_output_dir."""
    with pytest.raises(ValueError):
        load_config(_write_config(tmp_path, parquet_enabled=True))


def test_load_config_volume_mode_requires_positive_max_records(tmp_path: Path) -> None:
    """Volume mode requires positive parquet_max_records_per_file."""
    with pytest.raises(ValueError, match="parquet_max_records_per_file"):
        load_config(
            _write_config(
                tmp_path,
                parquet_enabled=True,
                parquet_output_dir="/tmp/parquet_out",
                parquet_batch_mode="volume",
                parquet_max_records_per_file=0,
            )
        )


def test_load_config_time_mode_requires_positive_flush_interval(tmp_path: Path) -> None:
    """Time mode requires positive parquet_flush_interval_seconds."""
    with pytest.raises(ValueError, match="parquet_flush_interval_seconds"):
        load_config(
            _write_config(
                tmp_path,
                parquet_enabled=True,
                parquet_output_dir="/tmp/parquet_out",
                parquet_batch_mode="time",
                parquet_flush_interval_seconds=0,
            )
        )


# ---------------------------------------------------------------------------
# CLI override mapping for parquet fields
# ---------------------------------------------------------------------------


def test_cli_overrides_parquet_fields(tmp_path: Path) -> None:
    config = load_config(
        _write_config(tmp_path, parquet_enabled=False),
        overrides={"parquet_enabled": True, "parquet_output_dir": "/tmp/new"},
    )
    assert config.parquet_enabled is True
    assert config.parquet_output_dir == Path("/tmp/new")


def test_cli_overrides_parquet_batch_mode(tmp_path: Path) -> None:
    config = load_config(
        _write_config(tmp_path, parquet_batch_mode="volume"),
        overrides={"parquet_batch_mode": "time"},
    )
    assert config.parquet_batch_mode == "time"


def test_cli_overrides_parquet_max_records_per_file(tmp_path: Path) -> None:
    config = load_config(
        _write_config(tmp_path, parquet_max_records_per_file=1000),
        overrides={"parquet_max_records_per_file": 2000},
    )
    assert config.parquet_max_records_per_file == 2000


def test_cli_overrides_parquet_flush_interval_seconds(tmp_path: Path) -> None:
    config = load_config(
        _write_config(tmp_path, parquet_flush_interval_seconds=1.0),
        overrides={"parquet_flush_interval_seconds": 30.0},
    )
    assert config.parquet_flush_interval_seconds == pytest.approx(30.0)


def test_cli_overrides_parquet_queue_capacity(tmp_path: Path) -> None:
    config = load_config(
        _write_config(tmp_path, parquet_queue_capacity=256),
        overrides={"parquet_queue_capacity": 512},
    )
    assert config.parquet_queue_capacity == 512
