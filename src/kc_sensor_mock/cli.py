from __future__ import annotations

import argparse


def _build_parser(prog: str, description: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=prog, description=description)


def run_server_cli() -> None:
    parser = _build_parser(
        "kc-sensor-mock",
        "Mock STM-style sensor stream server.",
    )
    parser.parse_args()


def run_client_cli() -> None:
    parser = _build_parser(
        "kc-sensor-client",
        "Reference client for the sensor mock stream.",
    )
    parser.parse_args()

