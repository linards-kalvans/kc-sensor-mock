"""Tests for CLI: producer/consumer entry points, endpoint fields, parquet flags."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from kc_sensor_mock import cli
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA


# ---------------------------------------------------------------------------
# Endpoint fields: AC-9
# ---------------------------------------------------------------------------


def test_producer_parser_has_consumer_endpoint_options() -> None:
    parser = cli.producer_parser()
    args = parser.parse_args([
        "--consumer-host", "10.0.0.5",
        "--consumer-port", "8080",
    ])
    assert args.consumer_host == "10.0.0.5"
    assert args.consumer_port == 8080


def test_consumer_parser_has_bind_endpoint_options() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args([
        "--bind-host", "0.0.0.0",
        "--bind-port", "9090",
    ])
    assert args.bind_host == "0.0.0.0"
    assert args.bind_port == 9090


def test_producer_parser_defaults_use_repo_root_config_path() -> None:
    parser = cli.producer_parser()
    args = parser.parse_args([])
    assert args.config == Path(cli.__file__).resolve().parents[2] / "configs" / "default.toml"
    assert args.consumer_host is None
    assert args.consumer_port is None


def test_consumer_parser_defaults_bind_to_loopback() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args([])
    assert args.bind_host is None
    assert args.bind_port is None


# ---------------------------------------------------------------------------
# Old naming removed: AC-10
# ---------------------------------------------------------------------------


def test_old_server_parser_does_not_exist() -> None:
    assert not hasattr(cli, "server_parser")


def test_old_client_parser_does_not_exist() -> None:
    assert not hasattr(cli, "client_parser")


def test_old_sensor_server_does_not_exist() -> None:
    try:
        from kc_sensor_mock.server import SensorServer  # noqa: F401
        pytest.fail("kc_sensor_mock.server.SensorServer still exists")
    except (ImportError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# New CLI entry points: AC-11
# ---------------------------------------------------------------------------


def test_run_producer_cli_exists() -> None:
    assert hasattr(cli, "run_producer_cli")


def test_run_consumer_cli_exists() -> None:
    assert hasattr(cli, "run_consumer_cli")


def test_run_producer_cli_loads_config_and_starts(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_load_config(path: Path, overrides: dict[str, object] | None = None) -> MockConfig:
        captured["path"] = path
        return MockConfig(
            consumer_host="127.0.0.1",
            consumer_port=9100,
            bind_host="127.0.0.1",
            bind_port=0,
            device_id=12,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            rate_hz=1000,
            mode="burst",
            ring_buffer_capacity=16,
            initial_sequence_number=0,
            gps_latitude=56.6718316,
            gps_longitude=24.2391946,
            gps_altitude_m=35.0,
            capture_path=None,
        )

    class FakeProducer:
        def __init__(self, config: MockConfig) -> None:
            captured["prod_config"] = config
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True
            captured["started"] = True

        def stop(self) -> None:
            self.stopped = True
            captured["stopped"] = True

    def fake_wait(prod: object) -> None:
        captured["waited"] = True

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "SensorProducerClient", FakeProducer)
    monkeypatch.setattr(cli, "_wait_for_shutdown", fake_wait)
    monkeypatch.setattr(sys, "argv", ["kc-sensor-producer", "--consumer-port", "9100"])

    cli.run_producer_cli()
    assert captured["started"] is True
    assert captured["waited"] is True
    assert captured["stopped"] is True


def test_run_consumer_cli_loads_config_and_starts(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_load_config(path: Path, overrides: dict[str, object] | None = None) -> MockConfig:
        captured["path"] = path
        return MockConfig(
            bind_host="0.0.0.0",
            bind_port=9090,
            consumer_host="127.0.0.1",
            consumer_port=8080,
            device_id=12,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            rate_hz=1000,
            mode="burst",
            ring_buffer_capacity=16,
            initial_sequence_number=0,
            gps_latitude=56.6718316,
            gps_longitude=24.2391946,
            gps_altitude_m=35.0,
            capture_path=None,
        )

    class FakeConsumer:
        def __init__(self, config: MockConfig) -> None:
            captured["cons_config"] = config
            self.host = "0.0.0.0"
            self.port = 9090

        def start(self) -> None:
            captured["started"] = True

        def stop(self) -> None:
            captured["stopped"] = True

    def fake_wait(consumer: object) -> None:
        captured["waited"] = True

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "SensorConsumerServer", FakeConsumer)
    monkeypatch.setattr(cli, "_wait_for_shutdown", fake_wait)
    monkeypatch.setattr(sys, "argv", ["kc-sensor-consumer"])

    cli.run_consumer_cli()
    assert captured["started"] is True
    assert captured["waited"] is True
    assert captured["stopped"] is True


# ---------------------------------------------------------------------------
# Parquet CLI flags: AC-4
# ---------------------------------------------------------------------------


def test_consumer_parser_has_parquet_enabled_flag() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args(["--parquet-enabled"])
    assert args.parquet_enabled is True


def test_consumer_parser_has_parquet_output_dir_flag() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args(["--parquet-output-dir", "/tmp/parquet_out"])
    assert args.parquet_output_dir == Path("/tmp/parquet_out")


def test_consumer_parser_has_parquet_batch_mode_flag() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args(["--parquet-batch-mode", "volume"])
    assert args.parquet_batch_mode == "volume"


def test_consumer_parser_has_parquet_max_records_per_file_flag() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args(["--parquet-max-records-per-file", "500"])
    assert args.parquet_max_records_per_file == 500


def test_consumer_parser_has_parquet_flush_interval_seconds_flag() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args(["--parquet-flush-interval-seconds", "5"])
    assert args.parquet_flush_interval_seconds == 5


def test_consumer_parser_has_parquet_queue_capacity_flag() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args(["--parquet-queue-capacity", "128"])
    assert args.parquet_queue_capacity == 128


def test_consumer_parser_parquet_defaults() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args([])
    assert args.parquet_enabled is False
    assert args.parquet_output_dir is None
    assert args.parquet_batch_mode is None
    assert args.parquet_max_records_per_file is None
    assert args.parquet_flush_interval_seconds is None
    assert args.parquet_queue_capacity is None


def test_consumer_parquet_flags_in_help_output(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.consumer_parser()
    help_text = parser.format_help()
    assert "--parquet-enabled" in help_text
    assert "--parquet-output-dir" in help_text
    assert "--parquet-batch-mode" in help_text
    assert "--parquet-max-records-per-file" in help_text
    assert "--parquet-flush-interval-seconds" in help_text
    assert "--parquet-queue-capacity" in help_text


# ---------------------------------------------------------------------------
# Parquet CLI override propagation: AC-4
# ---------------------------------------------------------------------------


def test_consumer_overrides_includes_parquet_fields_when_set() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args([
        "--parquet-enabled",
        "--parquet-output-dir", "/tmp/out",
        "--parquet-batch-mode", "time",
        "--parquet-max-records-per-file", "500",
        "--parquet-flush-interval-seconds", "5",
        "--parquet-queue-capacity", "128",
    ])
    overrides = cli._consumer_overrides(args)
    assert overrides.get("parquet_enabled") is True
    assert overrides.get("parquet_output_dir") == Path("/tmp/out")
    assert overrides.get("parquet_batch_mode") == "time"
    assert overrides.get("parquet_max_records_per_file") == 500
    assert overrides.get("parquet_flush_interval_seconds") == 5
    assert overrides.get("parquet_queue_capacity") == 128


def test_consumer_overrides_excludes_unset_parquet_fields() -> None:
    parser = cli.consumer_parser()
    args = parser.parse_args([])
    overrides = cli._consumer_overrides(args)
    assert "parquet_enabled" not in overrides
    assert "parquet_output_dir" not in overrides
    assert "parquet_batch_mode" not in overrides
    assert "parquet_max_records_per_file" not in overrides
    assert "parquet_flush_interval_seconds" not in overrides
    assert "parquet_queue_capacity" not in overrides


# ---------------------------------------------------------------------------
# Producer CLI: disabled parquet in shared config must not block startup
# ---------------------------------------------------------------------------


def test_producer_cli_loads_config_with_disabled_parquet_sentinels(monkeypatch, capsys) -> None:
    """Producer CLI must not fail when shared config has parquet_enabled=false and empty parquet fields.

    Regression: the producer uses shared config which has:
      parquet_enabled = false
      parquet_output_dir = ""
      parquet_batch_mode = ""
    These disabled sentinel values must not trigger parquet validation.
    """
    captured: dict[str, object] = {}

    def fake_load_config(path: Path, overrides: dict[str, object] | None = None) -> MockConfig:
        captured["path"] = path
        return MockConfig(
            consumer_host="127.0.0.1",
            consumer_port=9100,
            bind_host="127.0.0.1",
            bind_port=0,
            device_id=12,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            rate_hz=1000,
            mode="burst",
            ring_buffer_capacity=16,
            initial_sequence_number=0,
            gps_latitude=56.6718316,
            gps_longitude=24.2391946,
            gps_altitude_m=35.0,
            capture_path=None,
            parquet_enabled=False,
            parquet_output_dir=None,
            parquet_batch_mode=None,
        )

    class FakeProducer:
        def __init__(self, config: MockConfig) -> None:
            captured["prod_config"] = config
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True
            captured["started"] = True

        def stop(self) -> None:
            self.stopped = True
            captured["stopped"] = True

    def fake_wait(prod: object) -> None:
        captured["waited"] = True

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "SensorProducerClient", FakeProducer)
    monkeypatch.setattr(cli, "_wait_for_shutdown", fake_wait)
    monkeypatch.setattr(sys, "argv", ["kc-sensor-producer", "--consumer-port", "9100"])

    cli.run_producer_cli()
    assert captured["started"] is True
    assert captured["waited"] is True
    assert captured["stopped"] is True


def test_producer_cli_consumer_host_port_override_works(monkeypatch, capsys) -> None:
    """Producer CLI --consumer-host and --consumer-port overrides must still work.

    Regression: after fixing disabled parquet sentinel handling, consumer endpoint
    overrides must still propagate correctly.
    """
    captured: dict[str, object] = {}

    def fake_load_config(path: Path, overrides: dict[str, object] | None = None) -> MockConfig:
        captured["overrides"] = overrides
        return MockConfig(
            consumer_host="127.0.0.1",
            consumer_port=9100,
            bind_host="127.0.0.1",
            bind_port=0,
            device_id=12,
            measurement_type=MEASUREMENT_TYPE_SPECTRA,
            rate_hz=1000,
            mode="burst",
            ring_buffer_capacity=16,
            initial_sequence_number=0,
            gps_latitude=56.6718316,
            gps_longitude=24.2391946,
            gps_altitude_m=35.0,
            capture_path=None,
            parquet_enabled=False,
            parquet_output_dir=None,
            parquet_batch_mode=None,
        )

    class FakeProducer:
        def __init__(self, config: MockConfig) -> None:
            captured["prod_config"] = config
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True
            captured["started"] = True

        def stop(self) -> None:
            self.stopped = True
            captured["stopped"] = True

    def fake_wait(prod: object) -> None:
        captured["waited"] = True

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "SensorProducerClient", FakeProducer)
    monkeypatch.setattr(cli, "_wait_for_shutdown", fake_wait)
    monkeypatch.setattr(
        sys, "argv",
        ["kc-sensor-producer", "--consumer-host", "10.0.0.5", "--consumer-port", "8080"],
    )

    cli.run_producer_cli()
    assert captured["started"] is True
    assert captured["overrides"]["consumer_host"] == "10.0.0.5"
    assert captured["overrides"]["consumer_port"] == 8080
