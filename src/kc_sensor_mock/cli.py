from __future__ import annotations

import argparse
import signal
import sys
import threading
import tomllib
from pathlib import Path

from kc_sensor_mock.config import load_config
from kc_sensor_mock.consumer import SensorConsumerServer
from kc_sensor_mock.producer import SensorProducerClient


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "default.toml"


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def producer_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kc-sensor-producer",
        description="Mock STM-style sensor stream producer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=_default_config_path(), help="TOML config file to load")
    parser.add_argument("--consumer-host", dest="consumer_host", help="Consumer endpoint host override")
    parser.add_argument("--consumer-port", dest="consumer_port", type=int, help="Consumer endpoint port override")
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


def consumer_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kc-sensor-consumer",
        description="Reference consumer for the sensor mock stream.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=_default_config_path(), help="TOML config file to load")
    parser.add_argument("--bind-host", dest="bind_host", default=None, help="TCP bind host override (default: from config)")
    parser.add_argument("--bind-port", dest="bind_port", type=int, default=None, help="TCP bind port override (default: from config)")
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


def _producer_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    for name in (
        "consumer_host",
        "consumer_port",
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


def _consumer_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    for name in (
        "bind_host",
        "bind_port",
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


def _wait_for_shutdown(server: object) -> None:
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


def run_producer_cli() -> None:
    parser = producer_parser()
    args = parser.parse_args()
    producer: SensorProducerClient | None = None

    try:
        config = load_config(args.config, overrides=_producer_overrides(args))
        producer = SensorProducerClient(config)
        producer.start()
        print(f"producing to {config.consumer_host}:{config.consumer_port}")
        _wait_for_shutdown(producer)
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
        _raise_cli_error(parser, exc)
    except KeyboardInterrupt:
        pass
    finally:
        if producer is not None:
            producer.stop()


def run_consumer_cli() -> None:
    parser = consumer_parser()
    args = parser.parse_args()
    consumer: SensorConsumerServer | None = None

    try:
        config = load_config(args.config, overrides=_consumer_overrides(args))
        consumer = SensorConsumerServer(config)
        consumer.start()
        print(f"listening on {consumer.host}:{consumer.port}")
        _wait_for_shutdown(consumer)
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
        _raise_cli_error(parser, exc)
    except KeyboardInterrupt:
        pass
    finally:
        if consumer is not None:
            consumer.stop()
