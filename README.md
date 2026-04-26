# kc-sensor-mock

`kc-sensor-mock` is a Python mock of an STM-style sensor device. A producer connects outbound to a consumer listener and streams fixed binary sensor records over TCP so connector code can be exercised against a stable, C-friendly protocol.

## Protocol

- Each record is exactly `632` bytes.
- Records are little-endian.
- The stream contains repeated records only: no delimiter, header, length prefix, magic value, or checksum.
- Consumers must read exactly `632` bytes per record.

The binary layout is:

```text
<HHIIQQiii296H
```

That format corresponds to:

- `device_id`
- `measurement_type`
- `sequence_number`
- `dropped_records_total`
- `sensor_timestamp_us`
- `gps_timestamp_us`
- `gps_latitude_e7`
- `gps_longitude_e7`
- `gps_altitude_mm`
- `values[296]`

## Run

Start the consumer listener:

```bash
uv run kc-sensor-consumer
```

Start the producer and connect it to the consumer endpoint:

```bash
uv run kc-sensor-producer
```

Example with explicit endpoint overrides:

```bash
uv run kc-sensor-consumer --bind-host 127.0.0.1 --bind-port 9000
uv run kc-sensor-producer --consumer-host 127.0.0.1 --consumer-port 9000
```

## Parquet Export

The consumer can optionally export received sensor records to Apache Parquet files. A dedicated background writer thread receives records from the main receive path, so parquet writing does not block record ingestion.

### Enabling

Set `parquet_enabled = true` in the config file or pass `--parquet-enabled` on the CLI. When enabled, `parquet_output_dir` must also be set (config validation rejects the combination otherwise).

### Batching Modes

- **`volume`** (default when mode omitted): flushes a file when `parquet_max_records_per_file` records accumulate.
- **`time`**: flushes a file every `parquet_flush_interval_seconds`, writing whatever records are queued.

### Schema

Each parquet file contains one row per sensor record. The schema mirrors the sensor record fields; the `values` column is stored as a list of `uint16`.

```text
device_id:          uint16
measurement_type:   uint16
sequence_number:    uint32
dropped_records_total: uint32
sensor_timestamp_us: uint64
gps_timestamp_us:   uint64
gps_latitude_e7:    int32
gps_longitude_e7:   int32
gps_altitude_mm:    int32
values:             list<uint16>
```

### File Naming

Parquet output filenames follow a restart-safe pattern:

```
sensor-YYYYMMDDTHHMMSSZ-<mode>-<NNNN>-<seed>[-NN].parquet
```

- `YYYYMMDDTHHMMSSZ` — UTC timestamp at file creation time
- `<mode>` — active batch mode (`volume` or `time`)
- `<NNNN>` — zero-padded per-file counter (monotonic within a process)
- `<seed>` — 4-character hex random value generated at process start
- `[-NN]` — optional collision-retry suffix (appended only if the base
  filename already exists in the output directory)

The exporter reserves each output path atomically using exclusive file
creation (``open(path, 'x')`` / ``O_EXCL``).  If reservation fails
because the path already exists (e.g. same-second restart collision),
an incrementing `NN` suffix is appended and reservation is retried.
This atomic reservation guarantees no overwrite regardless of timestamp
overlap or seed collision, even under concurrent writers.

### Queue Overflow

The writer thread uses a bounded queue (`parquet_queue_capacity`, default 256). When the queue is full the oldest pending export record is dropped and a warning is logged (`"Parquet queue full — dropped 1 oldest record(s)"`). This is expected under sustained writer lag and does not affect the live TCP receive path.

### Shutdown

On graceful shutdown the writer thread flushes any remaining records in the queue before exiting, so partial batches are not lost.

### Configuration

| Config key | CLI flag | Type | Default | Description |
|---|---|---|---|---|
| `parquet_enabled` | `--parquet-enabled` | bool | `false` | Enable parquet export |
| `parquet_output_dir` | `--parquet-output-dir` | path | — | Output directory for parquet files (required when enabled) |
| `parquet_batch_mode` | `--parquet-batch-mode` | string | `volume` | `volume` or `time` |
| `parquet_max_records_per_file` | `--parquet-max-records-per-file` | int | `1000` | Records per file in volume mode |
| `parquet_flush_interval_seconds` | `--parquet-flush-interval-seconds` | float | `1.0` | Flush interval in time mode |
| `parquet_queue_capacity` | `--parquet-queue-capacity` | int | `256` | Max pending export records |

## Config

Default config lives in `configs/default.toml`.

Key transport fields:

- `bind_host`
- `bind_port`
- `consumer_host`
- `consumer_port`

Use `bind_*` for the consumer listener and `consumer_*` for the producer target endpoint.

## Testing

Run the normal test suite. Perf tests stay skipped by default:

```bash
uv run pytest -v
```

Run the perf lane explicitly when you want the high-rate check:

```bash
uv run pytest tests/perf/test_stream_rate.py --run-perf -s -v
```

## C Producer

A minimal standalone C producer lives under `c/`. It reads CSV sensor records and either writes concatenated little-endian binary wire-format to a file or streams them over TCP to a consumer endpoint.

### Build

```bash
make -C c clean all
```

### Verify serialization (emit-binary mode)

```bash
c/bin/c-producer --csv tests/c_fixtures/minimal_record.csv --emit-binary /tmp/c_emit.bin
sha256sum /tmp/c_emit.bin tests/c_fixtures/minimal_record.bin
```

The emitted file must be exactly 632 bytes and byte-identical to `tests/c_fixtures/minimal_record.bin`.

### End-to-end with Python consumer

Start the Python consumer listener:

```bash
uv run kc-sensor-consumer --bind-host 127.0.0.1 --bind-port 9000
```

In another terminal, stream records via the C producer:

```bash
c/bin/c-producer --csv tests/c_fixtures/minimal_record.csv --host 127.0.0.1 --port 9000
```

### Deferred features

The C producer is a minimal protocol-verification tool. The following features are deferred to a future production C implementation:

- **No rate control** — records are sent as fast as the TCP socket allows.
- **No reconnect** — if the TCP connection drops, the process exits.
- **No ring buffer** — all records are held in memory until sent.

## CLI Help

```bash
uv run kc-sensor-producer --help
uv run kc-sensor-consumer --help
```
