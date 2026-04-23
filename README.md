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

## CLI Help

```bash
uv run kc-sensor-producer --help
uv run kc-sensor-consumer --help
```
