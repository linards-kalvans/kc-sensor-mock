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
