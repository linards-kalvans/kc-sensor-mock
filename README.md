# kc-sensor-mock

`kc-sensor-mock` is a Python mock of an STM-style sensor device. It streams fixed binary sensor records over TCP so connector code can be exercised against a stable, C-friendly protocol.

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

Start the server with the default config:

```bash
uv run kc-sensor-mock
```

Connect with the reference client:

```bash
uv run kc-sensor-client --host 127.0.0.1 --port 9000 --count 10
```

## Testing

Run the normal test suite. Perf tests stay skipped by default:

```bash
uv run pytest tests -v
```

Run the perf lane explicitly when you want the high-rate check:

```bash
uv run pytest tests/perf/test_stream_rate.py --run-perf -s -v
```

## CLI Help

```bash
uv run kc-sensor-mock --help
uv run kc-sensor-client --help
```
