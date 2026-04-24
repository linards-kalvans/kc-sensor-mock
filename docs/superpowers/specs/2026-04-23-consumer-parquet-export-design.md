# Consumer Parquet Export Design

Date: 2026-04-23

## Purpose

Add an optional consumer-side parquet export feature for received sensor records. When enabled via CLI argument or config sourced from environment variables, the consumer writes received data to parquet files without interrupting the TCP receive path.

The feature exists to support downstream batch processing and archival of received mock sensor data. Predictable batch size is more important than time-window rotation by default, so volume-based batching is the preferred default. Time-based batching remains supported because it is useful for operations and time-window browsing.

## Scope

V1 includes:

- Optional parquet export on the consumer side.
- Runtime enablement via CLI/config/env-controlled settings.
- A dedicated writer thread so parquet work does not block receive-loop socket reads.
- Two batching policies:
  - `volume`: flush/rotate after a configured number of records.
  - `time`: flush/rotate after a configured interval.
- Default batching policy: `volume`.
- Parquet row format that mirrors one decoded sensor record per row.
- `values` stored as a parquet list/array column rather than 296 flattened scalar columns.
- Bounded in-memory export queue between consumer receive path and parquet writer.
- Drop-oldest behavior when export queue overflows.
- Traceable logs for parquet-export queue drops, including counts.
- Graceful shutdown flush of pending queued rows and final partial batch.
- Tests for happy path, batching, overflow, logging, and shutdown flush.

V1 excludes:

- Compression tuning or benchmark-driven codec selection.
- Schema evolution/versioning.
- Raw-byte archival mode as parquet export input.
- Multi-writer sharding, merge, or compaction.
- Replay/import from parquet back into the TCP stream.
- Metrics endpoint or external monitoring integration.

## Why Decoded-Record Export Is Preferred

The receive path could queue raw 632-byte payloads and defer decoding to a later batch stage, but that is not the preferred design.

Decoded-record queueing is preferred because:

- The fixed-size record decode cost is likely small compared with socket I/O, parquet encoding, compression, and file writes.
- The consumer already has a record-validity boundary at decode time, so keeping decode in the receive path preserves immediate validation.
- Queuing decoded records gives the writer thread a cleaner contract and avoids a second decode pass.
- Raw-first processing would add another ingest mode without solving the main problem, which is isolating parquet/file latency from the socket receive path.

Raw-first processing would only become worthwhile if profiling later proves fixed-record decoding is a real hotspot or if raw archival becomes a separate product requirement. Neither is in scope for this feature.

## Architecture

The parquet export path is consumer-only and sits behind the existing receive/decode path.

```text
Producer --> TCP socket --> Consumer recv loop --> decode_record(payload)
                                                      |
                                                      v
                                           bounded export queue
                                                      |
                                                      v
                                             parquet writer thread
                                                      |
                                                      v
                                            rotated parquet files
```

### Responsibilities

#### Consumer receive loop

- Reads exact fixed-size records from the producer connection.
- Decodes records immediately after `recv_exact` succeeds.
- Pushes decoded records into the bounded export queue when parquet export is enabled.
- Never waits on parquet file writes or parquet encoding work.

#### Export queue

- Holds decoded records awaiting parquet serialization.
- Has fixed maximum capacity.
- Uses drop-oldest behavior when full so new incoming records can still be queued.
- Tracks a consumer-local dropped-export-records counter.
- Emits warning logs with cumulative drop counts and relevant batch deltas.

#### Parquet writer thread

- Owns parquet/pyarrow objects and file lifecycle.
- Pulls decoded records from the queue.
- Converts them to parquet rows.
- Flushes and rotates files based on the active batching policy.
- Flushes remaining queued rows on clean shutdown.
- Treats parquet write failure as fatal when export is enabled.

## Data Model

Each parquet row represents one decoded sensor record.

Columns:

- `device_id`
- `measurement_type`
- `sequence_number`
- `dropped_records_total`
- `sensor_timestamp_us`
- `gps_timestamp_us`
- `gps_latitude_e7`
- `gps_longitude_e7`
- `gps_altitude_mm`
- `values`

`values` is stored as a list/array column of unsigned 16-bit values. This format is preferred over flattening into 296 scalar columns because it is lighter to transform, closer to the wire contract, and avoids an unnecessarily wide schema.

## Batching Policies

### Volume-based batching (default)

Flush and rotate parquet output after a configured number of rows.

Why this is preferred:

- Better fit for downstream batch jobs.
- More stable file sizes and row-group behavior.
- Less sensitive to idle periods, reconnect gaps, and clock-driven variance.

### Time-based batching

Flush and rotate parquet output after a configured time interval.

Why it is still supported:

- Helpful for operators who inspect data by time window.
- Useful for retention workflows based on time slices.

Only one batching policy is active at a time. V1 does not support hybrid “whichever comes first” rotation.

## Configuration Shape

Expected new consumer-facing configuration fields:

- `parquet_enabled: bool`
- `parquet_output_dir: Path`
- `parquet_batch_mode: Literal["volume", "time"]`
- `parquet_max_records_per_file: int | None`
- `parquet_flush_interval_seconds: float | None`
- `parquet_queue_capacity: int`

Rules:

- `parquet_enabled = false` means the consumer behaves exactly as today with no writer thread and no parquet files.
- `parquet_batch_mode = "volume"` requires `parquet_max_records_per_file`.
- `parquet_batch_mode = "time"` requires `parquet_flush_interval_seconds`.
- CLI arguments and environment-derived config can override file config.
- Volume mode is the default when parquet export is enabled and no batching mode is explicitly selected.

## File Naming

File names should be readable, restart-safe, and deterministic enough for tests.

Recommended shape:

```text
sensor-20260423T120000Z-volume-0001.parquet
sensor-20260423T120500Z-time-0002.parquet
```

Include:

- UTC batch/file start timestamp.
- Active batching mode.
- Monotonic file index or equivalent uniqueness suffix.

This prevents restart overwrite and gives operators enough context without additional metadata files.

## Shutdown Behavior

On clean consumer shutdown:

1. Stop accepting new export work.
2. Allow the parquet writer thread to drain queued decoded records.
3. Flush the final partial batch to a parquet file.
4. Exit after successful flush, or fail explicitly if the final flush cannot be completed.

This behavior is part of v1 success criteria because export files should remain useful when the process exits normally.

## Failure Handling

### Export queue overflow

If the parquet export queue is full:

- Drop the oldest queued export record.
- Enqueue the newest decoded record.
- Increment a consumer-local parquet drop counter.
- Emit traceable warning logs that include dropped counts.

This preserves the main requirement: parquet writing must not interrupt or stall the receive path.

### Parquet write failure

If parquet export is enabled and the writer thread encounters an unrecoverable write error:

- Log the error with file path/context.
- Treat the condition as fatal for the process.

The system should not silently continue receiving while pretending export is still healthy. Export failure is explicit and operationally visible.

### Malformed or partial TCP data

This feature does not change base consumer transport semantics:

- Partial or malformed records close the active producer connection.
- The consumer continues to accept future producer connections.
- These errors are separate from parquet queue overflow or file-write failures.

## Success Criteria

V1 is successful when all of the following are true:

- Consumer can run with parquet export disabled and behavior matches existing non-export path.
- Consumer can run with parquet export enabled in volume mode and produce parquet files after configured row thresholds.
- Consumer can run with parquet export enabled in time mode and produce parquet files after configured time intervals.
- Receive path does not wait for parquet writes.
- When the export queue overflows, oldest pending export records are dropped and warning logs include counts.
- On graceful shutdown, remaining queued rows and the final partial batch are flushed.
- Parquet rows match the decoded sensor records received by the consumer.
- Write failures in enabled export mode are explicit and fatal rather than silent.

## Testing Strategy

Automated tests should cover:

- Export disabled path creates no writer thread activity and no parquet files.
- Volume mode writes/rotates after configured record count.
- Time mode writes/rotates after configured interval.
- Queue overflow drops oldest queued export records and logs cumulative drop counts.
- Graceful shutdown flushes final partial batch.
- Persisted parquet rows match received decoded records.
- Artificially slow writer behavior does not block receive-path progress.
- File naming/rotation is deterministic under injected clock/test helpers.

Automated tests should not cover:

- Cross-platform filesystem performance tuning.
- Compression benchmarking.
- Multiple parallel parquet writers.
- Replay from parquet to TCP stream.

## Dependency Choice

Use `pyarrow` for parquet writing.

Why:

- Most standard Python parquet dependency for this use case.
- Strong parquet support and testability.
- Better fit for list/array column support for `values`.

## Future Revisit Triggers

Revisit this design only if one of these becomes true:

- Profiling shows fixed-record decode is a real receive-path bottleneck.
- Raw byte archival becomes a separate product requirement.
- Downstream users require schema flattening into 296 scalar columns.
- Export throughput requires multi-writer or partitioned output.
