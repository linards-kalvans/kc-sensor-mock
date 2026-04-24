"""Parquet export for consumer-side sensor record archival."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from kc_sensor_mock.protocol import SensorRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParquetExportConfig:
    output_dir: Path
    batch_mode: str
    max_records_per_file: int
    flush_interval_seconds: float
    queue_capacity: int


class ConsumerParquetExporter:
    """Exports decoded SensorRecords to parquet files in a background thread.

    Uses a bounded queue with drop-oldest on overflow.  Supports volume
    batching (flush when max_records_per_file reached) and time batching
    (flush after flush_interval_seconds).
    """

    def __init__(self, config: ParquetExportConfig) -> None:
        self._config = config
        self._queue: queue.Queue[SensorRecord | _FlushSentinel] = queue.Queue(
            maxsize=config.queue_capacity,
        )
        self._thread: threading.Thread | None = None
        self._stop_requested = threading.Event()
        self._stop_done = threading.Event()
        self._health_error: Exception | None = None
        self._health_lock = threading.Lock()
        # Per-file state (protected by self._lock)
        self._lock = threading.Lock()
        self._current_file_records: list[dict[str, Any]] = []
        self._file_counter = 0
        self._dir_created = False

    # -- public lifecycle ---------------------------------------------------

    def start(self) -> None:
        """Start the writer thread.  Fails immediately if output dir is invalid."""
        self._stop_requested.clear()
        self._stop_done.clear()
        self._health_error = None
        self._dir_created = False
        # Fail fast: output dir must be creatable at start time.
        self._ensure_dir()
        if self._health_error is not None:
            raise self._health_error from None
        self._thread = threading.Thread(
            target=self._write_loop,
            name="kc-sensor-parquet-writer",
            daemon=True,
        )
        self._thread.start()

    def submit(self, record: SensorRecord) -> None:
        """Submit a decoded record for parquet export.

        If the internal queue is full the oldest queued record is dropped
        and a warning is logged, then the new record is enqueued.
        """
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Drop oldest, then enqueue the new record
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            dropped_count = 1
            logger.warning(
                "Parquet queue full — dropped %d oldest record(s)", dropped_count
            )
            try:
                self._queue.put_nowait(record)
            except queue.Full:
                logger.warning("Parquet queue still full after drop — discarding record")

    def check_health(self) -> None:
        """Raise the last health error if one occurred."""
        err = self._health_error
        if err is not None:
            raise err

    def stop(self) -> None:
        """Signal the writer thread to stop and flush pending records."""
        self._stop_requested.set()
        # Signal a flush so pending records get written.
        try:
            self._queue.put_nowait(_FlushSentinel())
        except queue.Full:
            pass
        # Wait for the writer thread to finish.
        self._stop_done.wait(timeout=5.0)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    # -- internal -----------------------------------------------------------

    def _ensure_dir(self) -> None:
        """Create output directory if needed."""
        if self._dir_created:
            return
        try:
            self._config.output_dir.mkdir(parents=True, exist_ok=True)
            self._dir_created = True
        except OSError as exc:
            with self._health_lock:
                self._health_error = exc
            logger.error("Parquet output dir creation failed: %s", exc)

    def _write_loop(self) -> None:
        """Background writer loop.

        Drains the queue until ``_stop_requested`` is set and the queue
        is empty.  The ``_stop_done`` event is set when the loop exits
        so that ``stop()`` can reliably wait for completion even when
        the queue is saturated.
        """
        last_flush_time = time.monotonic()
        batch_mode = self._config.batch_mode
        max_records = self._config.max_records_per_file
        flush_interval = self._config.flush_interval_seconds

        while True:
            # When stop is requested and queue is empty, drain finished.
            if self._stop_requested.is_set() and self._queue.empty():
                break

            if self._stop_requested.is_set():
                timeout = 0.5
            else:
                timeout = 0.1

            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                # Time-based flush: runs in both modes so that partial
                # batches are eventually written when data flow slows.
                if self._current_file_records:
                    elapsed = time.monotonic() - last_flush_time
                    if elapsed >= flush_interval:
                        self._flush_batch()
                        last_flush_time = time.monotonic()
                continue

            if isinstance(item, _FlushSentinel):
                if self._current_file_records:
                    self._flush_batch()
                last_flush_time = time.monotonic()
                continue

            # It's a SensorRecord — ensure dir exists
            self._ensure_dir()

            if self._health_error is not None:
                # Dir creation failed, skip record
                continue

            with self._lock:
                self._current_file_records.append(self._record_to_dict(item))

            # Volume-based flush check
            if batch_mode == "volume" and len(self._current_file_records) >= max_records:
                self._flush_batch()
                last_flush_time = time.monotonic()

        # Final flush of any remaining records
        if self._current_file_records:
            self._flush_batch()

        self._stop_done.set()

    def _record_to_dict(self, record: SensorRecord) -> dict[str, Any]:
        return {
            "device_id": record.device_id,
            "measurement_type": record.measurement_type,
            "sequence_number": record.sequence_number,
            "dropped_records_total": record.dropped_records_total,
            "sensor_timestamp_us": record.sensor_timestamp_us,
            "gps_timestamp_us": record.gps_timestamp_us,
            "gps_latitude_e7": record.gps_latitude_e7,
            "gps_longitude_e7": record.gps_longitude_e7,
            "gps_altitude_mm": record.gps_altitude_mm,
            "values": list(record.values),
        }

    def _flush_batch(self) -> None:
        """Write current batch to a new parquet file."""
        with self._lock:
            if not self._current_file_records:
                return
            records = self._current_file_records
            self._current_file_records = []

        table = pa.table({
            "device_id": pa.array([r["device_id"] for r in records], type=pa.uint16()),
            "measurement_type": pa.array([r["measurement_type"] for r in records], type=pa.uint16()),
            "sequence_number": pa.array([r["sequence_number"] for r in records], type=pa.uint32()),
            "dropped_records_total": pa.array([r["dropped_records_total"] for r in records], type=pa.uint32()),
            "sensor_timestamp_us": pa.array([r["sensor_timestamp_us"] for r in records], type=pa.uint64()),
            "gps_timestamp_us": pa.array([r["gps_timestamp_us"] for r in records], type=pa.uint64()),
            "gps_latitude_e7": pa.array([r["gps_latitude_e7"] for r in records], type=pa.int32()),
            "gps_longitude_e7": pa.array([r["gps_longitude_e7"] for r in records], type=pa.int32()),
            "gps_altitude_mm": pa.array([r["gps_altitude_mm"] for r in records], type=pa.int32()),
            "values": pa.array([r["values"] for r in records], type=pa.list_(pa.uint16())),
        })

        self._file_counter += 1
        filename = f"sensor_{self._file_counter:06d}.parquet"
        filepath = self._config.output_dir / filename

        try:
            pq.write_table(table, filepath)
        except Exception as exc:
            with self._health_lock:
                self._health_error = exc
            logger.error("Parquet write failed: %s", exc)


class _FlushSentinel:
    """Marker to force a flush."""
