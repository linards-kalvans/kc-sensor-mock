"""Tests for the C producer binary (c/bin/c-producer).

These tests verify that the C producer can read the canonical CSV fixture
and emit binary output that matches the golden 632-byte record defined
in tests/test_protocol.py::test_encode_record_matches_golden_bytes.
"""

from __future__ import annotations

import socket
import threading
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = pathlib.Path(__file__).resolve().parent
FIXTURE_BIN = TESTS / "c_fixtures" / "minimal_record.bin"
FIXTURE_CSV = TESTS / "c_fixtures" / "minimal_record.csv"
C_PRODUCER = ROOT / "c" / "bin" / "c-producer"


def test_emit_binary_matches_golden_fixture() -> None:
    """c/bin/c-producer --csv <fixture> --emit-binary <out> must produce
    bytes identical to the golden 632-byte record fixture."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
        tmp_path = pathlib.Path(tmp.name)

    try:
        result = subprocess.run(
            [
                str(C_PRODUCER),
                "--csv",
                str(FIXTURE_CSV),
                "--emit-binary",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0, (
            f"c-producer exited with code {result.returncode}\n"
            f"stdout: {result.stdout.decode(errors='replace')}\n"
            f"stderr: {result.stderr.decode(errors='replace')}"
        )

        emitted = tmp_path.read_bytes()
        golden = FIXTURE_BIN.read_bytes()

        assert emitted == golden, (
            f"emitted {len(emitted)} bytes != golden {len(golden)} bytes\n"
            f"emitted hex (first 64): {emitted[:64].hex()}\n"
            f"golden  hex (first 64): {golden[:64].hex()}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_emit_binary_requires_csv_flag() -> None:
    """c/bin/c-producer --emit-binary <out> without --csv must return
    non-zero and print stderr mentioning --csv or usage."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
        tmp_path = pathlib.Path(tmp.name)

    try:
        result = subprocess.run(
            [
                str(C_PRODUCER),
                "--emit-binary",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=10,
        )

        assert result.returncode != 0, (
            "expected non-zero exit when --csv is missing"
        )

        stderr = result.stderr.decode(errors="replace")
        assert "--csv" in stderr or "usage" in stderr.lower(), (
            f"stderr should mention --csv or usage, got: {stderr}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_mixed_mode_rejected() -> None:
    """c/bin/c-producer --csv <fixture> --emit-binary <out> --host 127.0.0.1
    --port 1234 must return non-zero and mention mutual exclusion or usage."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
        tmp_path = pathlib.Path(tmp.name)

    try:
        result = subprocess.run(
            [
                str(C_PRODUCER),
                "--csv",
                str(FIXTURE_CSV),
                "--emit-binary",
                str(tmp_path),
                "--host",
                "127.0.0.1",
                "--port",
                "1234",
            ],
            capture_output=True,
            timeout=10,
        )

        assert result.returncode != 0, (
            "expected non-zero exit when both --emit-binary and --host are set"
        )

        stderr = result.stderr.decode(errors="replace")
        assert "mutual" in stderr.lower() or "usage" in stderr.lower(), (
            f"stderr should mention mutual exclusion or usage, got: {stderr}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_missing_mode_arguments_fail_with_usage() -> None:
    """c/bin/c-producer --csv <fixture> without --emit-binary must return
    non-zero and print usage hint mentioning --emit-binary."""
    result = subprocess.run(
        [
            str(C_PRODUCER),
            "--csv",
            str(FIXTURE_CSV),
        ],
        capture_output=True,
        timeout=10,
    )

    assert result.returncode != 0, (
        "expected non-zero exit when --emit-binary is missing"
    )

    stderr = result.stderr.decode(errors="replace")
    assert "--emit-binary" in stderr or "usage" in stderr.lower(), (
        f"stderr should mention --emit-binary or usage, got: {stderr}"
    )


def test_send_mode_streams_record_over_tcp() -> None:
    """c/bin/c-producer --csv <fixture> --host 127.0.0.1 --port <ephemeral>
    must connect, send one 632-byte record, exit 0, and the record must
    decode to the expected fixture values."""
    from kc_sensor_mock.consumer import recv_exact
    from kc_sensor_mock.protocol import RECORD_SIZE, decode_record

    # Start a Python TCP listener in a background thread
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    received: list[bytes] = []

    def accept_and_read() -> None:
        conn, _ = server.accept()
        data = recv_exact(conn, RECORD_SIZE)
        received.append(data)
        conn.close()
        server.close()

    t = threading.Thread(target=accept_and_read, daemon=True)
    t.start()

    try:
        result = subprocess.run(
            [
                str(C_PRODUCER),
                "--csv",
                str(FIXTURE_CSV),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            capture_output=True,
            timeout=10,
        )

        assert result.returncode == 0, (
            f"c-producer exited with code {result.returncode}\n"
            f"stdout: {result.stdout.decode(errors='replace')}\n"
            f"stderr: {result.stderr.decode(errors='replace')}"
        )

        t.join(timeout=5)
        assert len(received) == 1, f"expected 1 record, got {len(received)}"
        payload = received[0]
        assert len(payload) == RECORD_SIZE, (
            f"expected {RECORD_SIZE} bytes, got {len(payload)}"
        )

        record = decode_record(payload)
        assert record.device_id == 4660
        assert record.measurement_type == 2
        assert record.sequence_number == 16909060
        assert record.dropped_records_total == 84281096
        assert record.sensor_timestamp_us == 72623859790382856
        assert record.gps_timestamp_us == 1230066625199609624
        assert record.gps_latitude_e7 == -123456789
        assert record.gps_longitude_e7 == 168496141
        assert record.gps_altitude_mm == -1000
        assert record.values[0] == 258
        assert record.values[1] == 772
        assert record.values[2] == 1541
    finally:
        server.close()
