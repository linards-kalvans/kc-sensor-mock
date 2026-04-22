from __future__ import annotations

import argparse
import signal
import sys
import threading
import tomllib
from pathlib import Path

from kc_sensor_mock.client import read_records
from kc_sensor_mock.config import load_config
from kc_sensor_mock.server import SensorServer


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "default.toml"


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def server_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kc-sensor-mock",
        description="Mock STM-style sensor stream server.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=_default_config_path(), help="TOML config file to load")
    parser.add_argument("--host", help="TCP bind host override")
    parser.add_argument("--port", type=int, help="TCP bind port override")
    parser.add_argument("--device-id", type=int, dest="device_id", help="Sensor device identifier override")
    parser.add_argument(
        "--measurement-type",
        type=int,
        dest="measurement_type",
        help="Measurement type override",
    )
    parser.add_argument("--rate-hz", type=int, dest="rate_hz", help="Producer rate override")
    parser.add_argument(
        "--mode",
        choices=("rate-controlled", "burst"),
        help="Generator mode override",
    )
    parser.add_argument(
        "--ring-buffer-capacity",
        type=int,
        dest="ring_buffer_capacity",
        help="Ring buffer capacity override",
    )
    parser.add_argument("--capture-path", type=str, dest="capture_path", help="Capture file path override")
    return parser


def client_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kc-sensor-client",
        description="Reference client for the sensor mock stream.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="TCP host to connect to")
    parser.add_argument("--port", type=int, default=9000, help="TCP port to connect to")
    parser.add_argument("--count", type=_positive_int, default=10, help="Number of records to read")
    return parser


def _server_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    for name in (
        "host",
        "port",
        "device_id",
        "measurement_type",
        "rate_hz",
        "mode",
        "ring_buffer_capacity",
        "capture_path",
    ):
        value = getattr(args, name)
        if value is None:
            continue
        if name == "capture_path":
            overrides[name] = Path(value) if value else ""
            continue
        overrides[name] = value
    return overrides


def _stdin_shutdown_watcher(stop_event: threading.Event, stdin: object | None) -> threading.Thread | None:
    if stdin is None or getattr(stdin, "closed", False):
        return None

    def _watch_stdin() -> None:
        try:
            stdin.read()
        except (AttributeError, OSError, ValueError):
            return
        stop_event.set()

    watcher = threading.Thread(target=_watch_stdin, name="stdin-shutdown-watcher", daemon=True)
    watcher.start()
    return watcher


def _wait_for_shutdown(server: SensorServer) -> None:
    stop_event = threading.Event()
    previous_sigterm = None
    _stdin_shutdown_watcher(stop_event, sys.stdin)

    def _handle_sigterm(signum: int, frame: object) -> None:
        stop_event.set()

    if hasattr(signal, "SIGTERM"):
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        stop_event.wait()
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)


def _raise_cli_error(parser: argparse.ArgumentParser, exc: Exception) -> None:
    parser.error(str(exc))


def run_server_cli() -> None:
    parser = server_parser()
    args = parser.parse_args()
    server: SensorServer | None = None

    try:
        config = load_config(args.config, overrides=_server_overrides(args))
        server = SensorServer(config)
        server.start()
        print(f"streaming on {server.host}:{server.port}")
        _wait_for_shutdown(server)
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
        _raise_cli_error(parser, exc)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.stop()


def run_client_cli() -> None:
    parser = client_parser()
    args = parser.parse_args()

    try:
        records = read_records(args.host, args.port, args.count)
    except (OSError, ValueError) as exc:
        _raise_cli_error(parser, exc)

    for record in records:
        print(
            f"sequence={record.sequence_number} "
            f"device_id={record.device_id} "
            f"measurement_type={record.measurement_type} "
            f"dropped_records_total={record.dropped_records_total}"
        )
