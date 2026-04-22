from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from kc_sensor_mock import cli
from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, SensorRecord


def test_server_parser_defaults() -> None:
    parser = cli.server_parser()
    args = parser.parse_args([])

    assert args.config == Path("configs/default.toml")
    assert args.host is None
    assert args.port is None
    assert args.device_id is None
    assert args.measurement_type is None
    assert args.rate_hz is None
    assert args.mode is None
    assert args.ring_buffer_capacity is None
    assert args.capture_path is None


def test_client_parser_defaults() -> None:
    parser = cli.client_parser()
    args = parser.parse_args([])

    assert args.host == "127.0.0.1"
    assert args.port == 9000
    assert args.count == 10


def test_run_server_cli_loads_config_and_stops_on_eof(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_load_config(path: Path, overrides: dict[str, object] | None = None) -> MockConfig:
        captured["path"] = path
        captured["overrides"] = overrides
        return MockConfig(
            host="127.0.0.1",
            port=0,
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

    class FakeServer:
        def __init__(self, config: MockConfig) -> None:
            captured["server_config"] = config
            self.host = "127.0.0.1"
            self.port = 4321
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True
            captured["started"] = True

        def stop(self) -> None:
            self.stopped = True
            captured["stopped"] = True

    def fake_input() -> str:
        raise EOFError

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "SensorServer", FakeServer)
    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(sys, "argv", ["kc-sensor-mock", "--port", "9100", "--mode", "burst"])

    cli.run_server_cli()

    assert captured["path"] == Path("configs/default.toml")
    assert captured["overrides"] == {"port": 9100, "mode": "burst"}
    assert captured["started"] is True
    assert captured["stopped"] is True
    assert "streaming on 127.0.0.1:4321" in capsys.readouterr().out


def test_run_client_cli_prints_record_summaries(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}
    record = SensorRecord(
        device_id=7,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        sequence_number=3,
        dropped_records_total=1,
        sensor_timestamp_us=100,
        gps_timestamp_us=200,
        gps_latitude_e7=1,
        gps_longitude_e7=2,
        gps_altitude_mm=3,
        values=tuple(range(296)),
    )
    record_2 = replace(record, sequence_number=4, dropped_records_total=2)

    def fake_read_records(host: str, port: int, count: int) -> list[SensorRecord]:
        captured["args"] = (host, port, count)
        return [record, record_2]

    monkeypatch.setattr(cli, "read_records", fake_read_records)
    monkeypatch.setattr(sys, "argv", ["kc-sensor-client", "--host", "localhost", "--port", "9100", "--count", "2"])

    cli.run_client_cli()

    assert captured["args"] == ("localhost", 9100, 2)
    output = capsys.readouterr().out.splitlines()
    assert output == [
        "sequence=3 device_id=7 measurement_type=1 dropped_records_total=1",
        "sequence=4 device_id=7 measurement_type=1 dropped_records_total=2",
    ]
