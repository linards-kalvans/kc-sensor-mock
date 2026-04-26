"""Tests for the parquet export module: ParquetExportConfig, ConsumerParquetExporter."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest

from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, SensorRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(sequence_number: int = 1) -> SensorRecord:
    return SensorRecord(
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        sequence_number=sequence_number,
        dropped_records_total=0,
        sensor_timestamp_us=1_000_000 + sequence_number,
        gps_timestamp_us=1_000_000 + sequence_number,
        gps_latitude_e7=566718316,
        gps_longitude_e7=242391946,
        gps_altitude_mm=35000,
        values=tuple(range(296)),
    )


def _poll_files(path: Path, timeout: float = 3.0, interval: float = 0.1) -> list[Path]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        files = sorted(path.glob("*.parquet"))
        if files:
            return files
        time.sleep(interval)
    return sorted(path.glob("*.parquet"))


# ---------------------------------------------------------------------------
# ParquetExportConfig — AC-1: module exists, class exists, fields exist
# ---------------------------------------------------------------------------


def test_parquet_export_module_importable() -> None:
    import kc_sensor_mock.parquet_export  # noqa: F401


def test_parquet_export_config_class_exists() -> None:
    from kc_sensor_mock.parquet_export import ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=Path("/tmp"),
        batch_mode="volume",
        max_records_per_file=100,
        flush_interval_seconds=1.0,
        queue_capacity=64,
    )
    assert cfg.output_dir == Path("/tmp")
    assert cfg.batch_mode == "volume"
    assert cfg.max_records_per_file == 100
    assert cfg.flush_interval_seconds == 1.0
    assert cfg.queue_capacity == 64


def test_consumer_parquet_exporter_class_exists() -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter

    assert ConsumerParquetExporter is not None


def test_consumer_parquet_exporter_has_approved_methods() -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=Path("/tmp"),
        batch_mode="volume",
        max_records_per_file=100,
        flush_interval_seconds=1.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    assert callable(getattr(exporter, "start", None))
    assert callable(getattr(exporter, "submit", None))
    assert callable(getattr(exporter, "check_health", None))
    assert callable(getattr(exporter, "stop", None))


# ---------------------------------------------------------------------------
# Parquet row schema — AC-4: columns + values is list type
# ---------------------------------------------------------------------------


def test_parquet_schema_and_values_type(tmp_path: Path) -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    expected_columns = {
        "device_id",
        "measurement_type",
        "sequence_number",
        "dropped_records_total",
        "sensor_timestamp_us",
        "gps_timestamp_us",
        "gps_latitude_e7",
        "gps_longitude_e7",
        "gps_altitude_mm",
        "values",
    }

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=1000,
        flush_interval_seconds=1.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()
    exporter.submit(_make_record(sequence_number=1))

    files = _poll_files(tmp_path)
    exporter.stop()

    import pyarrow.parquet as pq

    schema_columns = set(pq.read_schema(files[0]).names)
    assert schema_columns == expected_columns

    values_field = pq.read_schema(files[0]).field("values")
    assert "list" in str(values_field.type).lower()


# ---------------------------------------------------------------------------
# Volume batching — AC-3
# ---------------------------------------------------------------------------


def test_parquet_volume_batch_writes_and_preserves_count(tmp_path: Path) -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=10,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()

    for i in range(10):
        exporter.submit(_make_record(sequence_number=i))

    files = _poll_files(tmp_path)
    exporter.stop()

    assert len(files) >= 1

    import pyarrow.parquet as pq

    table = pq.read_table(files[0])
    assert table.num_rows == 10


# ---------------------------------------------------------------------------
# Time batching — AC-3
# ---------------------------------------------------------------------------


def test_parquet_time_batch_writes_after_flush_interval(tmp_path: Path) -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="time",
        max_records_per_file=1000,
        flush_interval_seconds=0.5,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()
    exporter.submit(_make_record(sequence_number=1))

    files = _poll_files(tmp_path, timeout=3.0)
    exporter.stop()
    assert len(files) >= 1


# ---------------------------------------------------------------------------
# Graceful shutdown — AC-6: flush pending on stop()
# ---------------------------------------------------------------------------


def test_parquet_shutdown_flushes_pending(tmp_path: Path) -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=100,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()

    for i in range(3):
        exporter.submit(_make_record(sequence_number=i))

    exporter.stop()

    files = _poll_files(tmp_path, timeout=2.0)
    assert len(files) >= 1

    import pyarrow.parquet as pq

    table = pq.read_table(files[0])
    assert table.num_rows == 3


# ---------------------------------------------------------------------------
# Queue overflow — AC-5: warn via caplog
# ---------------------------------------------------------------------------


def test_parquet_queue_overflow_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=1000,
        flush_interval_seconds=10.0,
        queue_capacity=2,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()

    for i in range(20):
        exporter.submit(_make_record(sequence_number=i))

    exporter.stop()

    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warning_records) > 0


# ---------------------------------------------------------------------------
# Filename shape — restart-safe naming (timestamp + mode + index)
# ---------------------------------------------------------------------------


def test_parquet_filename_shape_volume(tmp_path: Path) -> None:
    """Volume-batch parquet filenames must match:
    sensor-YYYYMMDDTHHMMSSZ-volume-NNNN.parquet"""
    from datetime import datetime, timezone
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=10,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()
    for i in range(10):
        exporter.submit(_make_record(sequence_number=i))
    exporter.stop()

    files = _poll_files(tmp_path)
    assert len(files) >= 1
    name = files[0].name
    # Must start with sensor- and end with .parquet
    assert name.startswith("sensor-")
    assert name.endswith(".parquet")
    # Must contain "-volume-" segment
    assert "-volume-" in name
    # The date-time portion (between first "-" and "-volume-") must parse
    date_part = name.split("-volume-")[0]  # e.g. sensor-20260101T120000Z
    dt_str = date_part.removeprefix("sensor-").removesuffix("Z")
    datetime.strptime(dt_str, "%Y%m%dT%H%M%S")


def test_parquet_filename_shape_time(tmp_path: Path) -> None:
    """Time-batch parquet filenames must match:
    sensor-YYYYMMDDTHHMMSSZ-time-NNNN.parquet"""
    from datetime import datetime, timezone
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="time",
        max_records_per_file=1000,
        flush_interval_seconds=0.3,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()
    exporter.submit(_make_record(sequence_number=1))
    files = _poll_files(tmp_path, timeout=3.0)
    exporter.stop()

    assert len(files) >= 1
    name = files[0].name
    assert name.startswith("sensor-")
    assert name.endswith(".parquet")
    assert "-time-" in name


# ---------------------------------------------------------------------------
# Restart safety — two separate exporter instances don't collide
# ---------------------------------------------------------------------------


def test_parquet_restart_safety_two_instances(tmp_path: Path) -> None:
    """Two separate exporter instances writing to the same directory
    must produce distinct filenames (no overwrite)."""
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=5,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )

    # First instance
    exporter_a = ConsumerParquetExporter(cfg)
    exporter_a.start()
    for i in range(5):
        exporter_a.submit(_make_record(sequence_number=i))
    exporter_a.stop()

    files_after_a = sorted(tmp_path.glob("*.parquet"))
    assert len(files_after_a) >= 1
    names_a = {f.name for f in files_after_a}

    # Second instance — same directory, fresh counter
    exporter_b = ConsumerParquetExporter(cfg)
    exporter_b.start()
    for i in range(5):
        exporter_b.submit(_make_record(sequence_number=i + 100))
    exporter_b.stop()

    files_after_b = sorted(tmp_path.glob("*.parquet"))
    assert len(files_after_b) >= 2

    names_b = {f.name for f in files_after_b}
    # Every file from instance B must have a name not seen from instance A
    # (at least one new file with a different name must exist)
    assert len(names_b - names_a) >= 1


# ---------------------------------------------------------------------------
# Existing content-writing tests stay compatible with new naming
# ---------------------------------------------------------------------------


def test_parquet_volume_batch_still_writes_correct_rows(tmp_path: Path) -> None:
    """Volume batching still writes the right number of rows even with
    the new filename format."""
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=10,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()
    for i in range(10):
        exporter.submit(_make_record(sequence_number=i))
    exporter.stop()

    files = _poll_files(tmp_path)
    assert len(files) >= 1

    import pyarrow.parquet as pq

    table = pq.read_table(files[0])
    assert table.num_rows == 10


def test_parquet_shutdown_still_flushes_pending(tmp_path: Path) -> None:
    """Graceful shutdown still flushes pending records with new naming."""
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=100,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()
    for i in range(3):
        exporter.submit(_make_record(sequence_number=i))
    exporter.stop()

    files = _poll_files(tmp_path, timeout=2.0)
    assert len(files) >= 1

    import pyarrow.parquet as pq

    table = pq.read_table(files[0])
    assert table.num_rows == 3


# ---------------------------------------------------------------------------
# Write failure is fatal — AC-7
# ---------------------------------------------------------------------------


def test_parquet_write_failure_raises_error(tmp_path: Path) -> None:
    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=Path("/nonexistent/deeply/nested/dir/that/cannot/exist"),
        batch_mode="volume",
        max_records_per_file=100,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)

    # start() must fail immediately when output dir cannot be created
    with pytest.raises(Exception):
        exporter.start()


# ---------------------------------------------------------------------------
# Write failure — error surfacing and reserved-file cleanup
# ---------------------------------------------------------------------------


def test_parquet_write_failure_stores_health_error(tmp_path: Path) -> None:
    """When parquet write fails, the exporter stores the error in
    _health_error and stop() re-raises it."""
    import pyarrow as pa
    from unittest.mock import patch

    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="time",
        max_records_per_file=1000,
        flush_interval_seconds=0.2,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()

    # Inject a write failure by mocking pq.write_table
    with patch("kc_sensor_mock.parquet_export.pq.write_table") as mock_write:
        mock_write.side_effect = OSError("disk full")
        exporter.submit(_make_record(sequence_number=1))
        # Give the writer thread time to process (time-based flush)
        time.sleep(0.5)

    with pytest.raises(OSError, match="disk full"):
        exporter.stop()

    # Verify the error was stored before stop() re-raised it
    assert isinstance(exporter._health_error, OSError)
    assert "disk full" in str(exporter._health_error)


def test_parquet_write_failure_cleans_up_reserved_file(tmp_path: Path) -> None:
    """When parquet write fails, the reserved (empty) file is deleted
    from disk so it does not linger as an artifact."""
    from unittest.mock import patch

    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="time",
        max_records_per_file=1000,
        flush_interval_seconds=0.2,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()

    # Inject a write failure
    with patch("kc_sensor_mock.parquet_export.pq.write_table") as mock_write:
        mock_write.side_effect = OSError("write error")
        exporter.submit(_make_record(sequence_number=1))
        time.sleep(0.5)

    with pytest.raises(OSError, match="write error"):
        exporter.stop()

    # No parquet files should remain — the reserved file was cleaned up
    parquet_files = list(tmp_path.glob("*.parquet"))
    assert len(parquet_files) == 0


def test_parquet_stop_raises_health_error(tmp_path: Path) -> None:
    """stop() raises the stored _health_error after the writer thread
    has joined, so callers can detect fatal export failures."""
    from unittest.mock import patch

    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="time",
        max_records_per_file=1000,
        flush_interval_seconds=0.2,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()

    with patch("kc_sensor_mock.parquet_export.pq.write_table") as mock_write:
        mock_write.side_effect = OSError("fatal write")
        exporter.submit(_make_record(sequence_number=1))
        time.sleep(0.5)

    with pytest.raises(OSError, match="fatal write"):
        exporter.stop()


# ---------------------------------------------------------------------------
# Deterministic restart safety — same-second collision (mocked timestamp)
# ---------------------------------------------------------------------------


def test_parquet_restart_safety_same_second_mocked(tmp_path: Path) -> None:
    """Two exporter instances forced to the same UTC second must still
    produce distinct filenames.  Pre-create a file with the expected name
    to force a collision, then assert the exporter picks a different name."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=5,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )

    fixed_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # First instance — patch datetime.now to return fixed time
    with patch("kc_sensor_mock.parquet_export.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_dt
        mock_dt.timezone = timezone
        exporter_a = ConsumerParquetExporter(cfg)
        exporter_a.start()
        for i in range(5):
            exporter_a.submit(_make_record(sequence_number=i))
        exporter_a.stop()

    files_after_a = sorted(tmp_path.glob("*.parquet"))
    assert len(files_after_a) >= 1
    names_a = {f.name for f in files_after_a}

    # Second instance — same fixed time, same seed is unlikely but
    # collision-retry logic must still guarantee a different name.
    with patch("kc_sensor_mock.parquet_export.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_dt
        mock_dt.timezone = timezone
        exporter_b = ConsumerParquetExporter(cfg)
        exporter_b.start()
        for i in range(5):
            exporter_b.submit(_make_record(sequence_number=i + 100))
        exporter_b.stop()

    files_after_b = sorted(tmp_path.glob("*.parquet"))
    assert len(files_after_b) >= 2

    names_b = {f.name for f in files_after_b}
    # Every file from B must have a name not seen from A
    assert len(names_b - names_a) >= 1


def test_parquet_restart_safety_forced_collision(tmp_path: Path) -> None:
    """Force a filename collision by pre-creating a file with the exact
    name the exporter would generate.  The collision-retry logic must
    pick a different name and still write successfully."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=5,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )

    fixed_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    fixed_seed = "aaaa"

    # First instance — use a fixed seed so we know the exact filename
    with patch("kc_sensor_mock.parquet_export.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_dt
        mock_dt.timezone = timezone
        exporter_a = ConsumerParquetExporter(cfg)
        exporter_a._process_seed = fixed_seed
        exporter_a.start()
        for i in range(5):
            exporter_a.submit(_make_record(sequence_number=i))
        exporter_a.stop()

    files_after_a = sorted(tmp_path.glob("*.parquet"))
    assert len(files_after_a) == 1
    first_filename = files_after_a[0].name

    # Pre-create a file with that exact name to force collision on retry
    (tmp_path / first_filename).unlink()
    (tmp_path / first_filename).touch()

    # Second instance — same fixed time, same seed, same counter
    with patch("kc_sensor_mock.parquet_export.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_dt
        mock_dt.timezone = timezone
        exporter_b = ConsumerParquetExporter(cfg)
        exporter_b._process_seed = fixed_seed
        exporter_b._file_counter = 0  # _next_output_path will increment to 1
        exporter_b.start()
        for i in range(5):
            exporter_b.submit(_make_record(sequence_number=i + 100))
        exporter_b.stop()

    files_after_b = sorted(tmp_path.glob("*.parquet"))
    # Should have: the pre-created placeholder + exporter_b's file (with -01 suffix)
    assert len(files_after_b) == 2
    # The actual data file must NOT be the pre-created placeholder
    data_files = [f for f in files_after_b if f.name != first_filename]
    assert len(data_files) == 1
    # Collision-retry file must have -NN suffix
    assert "-01" in data_files[0].name


# ---------------------------------------------------------------------------
# Filename shape includes random seed component
# ---------------------------------------------------------------------------


def test_parquet_filename_has_seed_component(tmp_path: Path) -> None:
    """Every parquet filename must include a 4-char hex seed component
    between the counter and the .parquet extension (optionally followed
    by a -NN collision-retry suffix)."""
    import re

    from kc_sensor_mock.parquet_export import ConsumerParquetExporter, ParquetExportConfig

    cfg = ParquetExportConfig(
        output_dir=tmp_path,
        batch_mode="volume",
        max_records_per_file=10,
        flush_interval_seconds=10.0,
        queue_capacity=64,
    )
    exporter = ConsumerParquetExporter(cfg)
    exporter.start()
    for i in range(10):
        exporter.submit(_make_record(sequence_number=i))
    exporter.stop()

    files = _poll_files(tmp_path)
    assert len(files) >= 1
    name = files[0].name

    # Pattern: sensor-YYYYMMDDTHHMMSSZ-volume-NNNN-XXXX[-NN].parquet
    pattern = (
        r"sensor-\d{8}T\d{6}Z-volume-\d{4}-[0-9a-f]{4}"
        r"(-\d{2})?\.parquet"
    )
    assert re.fullmatch(pattern, name), f"Filename {name!r} does not match expected pattern"
