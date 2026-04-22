from __future__ import annotations

import argparse
from pathlib import Path

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import load_config
from kc_sensor_mock.server import SensorServer


def server_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kc-sensor-mock", description="Mock STM-style sensor stream server.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/default.toml"),
    )
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--device-id", type=int, dest="device_id")
    parser.add_argument("--measurement-type", type=int, dest="measurement_type")
    parser.add_argument("--rate-hz", type=int, dest="rate_hz")
    parser.add_argument("--mode", choices=("rate-controlled", "burst"))
    parser.add_argument("--ring-buffer-capacity", type=int, dest="ring_buffer_capacity")
    parser.add_argument("--capture-path", type=Path, dest="capture_path")
    return parser


def client_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kc-sensor-client",
        description="Reference client for the sensor mock stream.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--count", type=int, default=10)
    return parser


def _server_overrides(args: argparse.Namespace) -> dict[str, object]:
    override_names = (
        "host",
        "port",
        "device_id",
        "measurement_type",
        "rate_hz",
        "mode",
        "ring_buffer_capacity",
        "capture_path",
    )
    return {
        name: getattr(args, name)
        for name in override_names
        if getattr(args, name) is not None
    }


def run_server_cli() -> None:
    args = server_parser().parse_args()
    config = load_config(args.config, overrides=_server_overrides(args))
    server = SensorServer(config)
    server.start()
    print(f"streaming on {server.host}:{server.port}")

    try:
        while True:
            input()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        server.stop()


def run_client_cli() -> None:
    args = client_parser().parse_args()
    records = read_records(args.host, args.port, args.count)
    for record in records:
        print(
            f"sequence={record.sequence_number} "
            f"device_id={record.device_id} "
            f"measurement_type={record.measurement_type} "
            f"dropped_records_total={record.dropped_records_total}"
        )
