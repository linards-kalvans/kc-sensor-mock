from __future__ import annotations

import subprocess
from pathlib import Path


def test_package_import_exposes_metadata() -> None:
    import kc_sensor_mock

    assert kc_sensor_mock.__package_name__ == "kc-sensor-mock"
    assert kc_sensor_mock.__version__ == "0.1.0"


def test_server_console_script_help_exits_successfully() -> None:
    result = subprocess.run(
        ["uv", "run", "kc-sensor-mock", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_client_console_script_help_exits_successfully() -> None:
    result = subprocess.run(
        ["uv", "run", "kc-sensor-client", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
