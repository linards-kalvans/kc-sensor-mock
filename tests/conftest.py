from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-perf",
        action="store_true",
        default=False,
        help="run tests marked with @pytest.mark.perf",
    )


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    if config.getoption("--run-perf"):
        return False

    parts = collection_path.parts
    for index in range(len(parts) - 1):
        if parts[index] == "tests" and parts[index + 1] == "perf":
            return True

    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-perf"):
        return

    skip_perf = pytest.mark.skip(reason="run with --run-perf to execute perf tests")
    for item in items:
        if "perf" in item.keywords:
            item.add_marker(skip_perf)
