"""Tests for CLI: producer/consumer entry points, endpoint fields."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from kc_sensor_mock import cli
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA


# --- AC-9: Config and CLI reflect explicit producer/consumer endpoint fields ---

def test_producer_parser_has_consumer_endpoint_options() -> None:
    """kc-sensor-producer parser must expose --consumer-host and --consumer-port."""
    parser = cli.producer_parser()
    args = parser.parse_args([
        "--consumer-host", "10.0.0.5",
        "--consumer-port", "8080",
    ])

    assert args.consumer_host == "10.0.0.5"
    assert args.consumer_port == 8080


def test_consumer_parser_has_bind_endpoint_options() -> None:
    """kc-sensor-consumer parser must expose --bind-host and --bind-port."""
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


# --- AC-10: Old transport naming no longer defines public CLI contract ---

def test_old_server_parser_does_not_exist() -> None:
    """The old `server_parser` name must not exist on the cli module."""
    assert not hasattr(cli, "server_parser"), (
        "cli.server_parser must be removed — replaced by producer_parser"
    )


def test_old_client_parser_does_not_exist() -> None:
    """The old `client_parser` name must not exist on the cli module."""
    assert not hasattr(cli, "client_parser"), (
        "cli.client_parser must be removed — replaced by consumer_parser"
    )


def test_old_sensor_server_does_not_exist() -> None:
    """SensorServer must be gone from imports."""
    try:
        from kc_sensor_mock.server import SensorServer  # noqa: F401
        pytest.fail("kc_sensor_mock.server.SensorServer still exists")
    except (ImportError, AttributeError):
        pass


# --- AC-11: New CLI run functions exist ---

def test_run_producer_cli_exists() -> None:
    assert hasattr(cli, "run_producer_cli"), "cli must expose run_producer_cli"


def test_run_consumer_cli_exists() -> None:
    assert hasattr(cli, "run_consumer_cli"), "cli must expose run_consumer_cli"


def test_run_producer_cli_loads_config_and_starts(monkeypatch, capsys) -> None:
    """Producer CLI loads config, starts producer, waits for shutdown."""
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
    """Consumer CLI loads config, starts consumer, waits for shutdown."""
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
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True
            captured["started"] = True

        def stop(self) -> None:
            self.stopped = True
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


def test_consumer_help_shows_bind_defaults(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.consumer_parser()
    help_text = parser.format_help()

    assert "(default: None)" in help_text
