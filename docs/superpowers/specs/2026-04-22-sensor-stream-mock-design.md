# Sensor Stream Mock Design

Date: 2026-04-22

## Purpose

Build a mock application that simulates an STM-style C sensor device. The mock must produce fixed binary records, buffer them through a ring buffer, and stream them over TCP to a consumer. The first implementation will be Python, but the protocol must be precise enough to support a later C implementation without changing the connector contract.

The main goal is connector development and throughput validation for a future physical consumer. Bandwidth and I/O efficiency are important, so the default TCP stream is repeated fixed-size records with no transport frame header, delimiter, or per-record checksum.

## V1 Scope

V1 includes:

- A fixed little-endian binary record specification.
- Python pack/unpack support for the record.
- A sample-like data generator using 296 spectral values per record.
- Two measurement types:
  - `1`: spectra
  - `2`: background spectra
- A fixed-capacity ring buffer that drops oldest records when full.
- An inbound TCP listener (consumer) that accepts one producer connection at a time.
- An outbound TCP client (producer) that connects to the consumer and streams records continuously.
- Config file support with CLI overrides.
- Rate-controlled mode, defaulting to `1000 Hz`.
- Burst mode for maximum sustained throughput testing.
- Optional raw binary capture of the exact records written to TCP.
- Automated tests for protocol, buffering, generation, and TCP smoke behavior.
- A separately runnable performance check for high-rate streaming.

V1 excludes:

- Multi-client fan-out.
- Command/control messages.
- TCP frame headers.
- Record delimiters or breaks.
- Per-record checksums.
- Variable-length records.
- Field or farm metadata in the sensor record.
- Production C implementation.

## Binary Record Contract

The stream is a sequence of fixed-size records. There is no record delimiter, TCP-level frame header, magic value, length prefix, or per-record checksum. Consumers must read exactly `sizeof(sensor_record_t)` bytes for each record.

TCP provides ordered byte-stream delivery. If network packet loss occurs, TCP retransmits below the application layer. If TCP cannot recover, the connection fails or closes; the consumer should reconnect and use `sequence_number` plus `dropped_records_total` to detect records missed during disconnects or buffer overflow. V1 does not support mid-stream byte resynchronization after a consumer loses record alignment.

All fields are little-endian and fixed-width. The Python implementation must use explicit struct packing. The later C implementation must use fixed-width integer types and packed layout or equivalent byte serialization.

Proposed C shape:

```c
#define SENSOR_VALUES_COUNT 296
#define MEASUREMENT_TYPE_SPECTRA 1
#define MEASUREMENT_TYPE_BACKGROUND_SPECTRA 2

typedef struct {
    uint16_t device_id;
    uint16_t measurement_type;
    uint32_t sequence_number;
    uint32_t dropped_records_total;
    uint64_t sensor_timestamp_us;
    uint64_t gps_timestamp_us;
    int32_t gps_latitude_e7;
    int32_t gps_longitude_e7;
    int32_t gps_altitude_mm;
    uint16_t values[SENSOR_VALUES_COUNT];
} sensor_record_t;
```

Packed size without padding is `632` bytes:

- Metadata: `40` bytes.
- Values: `296 * 2 = 592` bytes.

The Python struct format is:

```text
<HHIIQQiii296H
```

Field meanings:

- `device_id`: physical or simulated device identifier.
- `measurement_type`: indicates whether `values` contains spectra or background spectra.
- `sequence_number`: monotonically increasing per produced record, starting at a configured initial value, default `0`.
- `dropped_records_total`: cumulative number of records dropped by the producer-side ring buffer.
- `sensor_timestamp_us`: mock sensor timestamp in microseconds.
- `gps_timestamp_us`: GPS timestamp as Unix epoch microseconds in UTC.
- `gps_latitude_e7`: latitude degrees multiplied by `10,000,000`.
- `gps_longitude_e7`: longitude degrees multiplied by `10,000,000`.
- `gps_altitude_mm`: altitude meters multiplied by `1,000`.
- `values`: exactly 296 unsigned 16-bit sensor values.

`field_name` and `field_id` are not included. They are consumer-side configuration concerns, not physical sensor payload.

## Data Generation

The default generator replays sample-like records based on the provided spectra example. The generated record must always contain exactly 296 values. If input sample data differs from 296 values, the generator must fail validation rather than silently truncate or pad.

The generator updates:

- `sequence_number`
- `sensor_timestamp_us`
- `gps_timestamp_us`
- scaled GPS coordinates
- `dropped_records_total`

Default measurement output is spectra. Background spectra generation uses the same fixed values array and sets `measurement_type` to `2`.

Future synthetic generators may be added, but V1 should implement replay/sample-like generation first.

## Buffering

The producer writes generated records into a fixed-capacity ring buffer. When the buffer is full, it drops the oldest record and increments `dropped_records_total`.

This behavior preserves the most recent sensor data and exposes missed data through sequence gaps and the dropped-record counter.

Default capacity: `4096` records, configurable.

## TCP Streaming

The consumer runs one inbound TCP listener and accepts one producer connection at a time. After a producer connects, the consumer accepts the stream. The producer connects outbound to the consumer bind address, reads records from its ring buffer, and writes packed records to the socket continuously.

The stream contains only repeated binary records:

```text
[record][record][record]...
```

No length prefix, magic bytes, checksums, delimiters, JSON, or text logs are included in the TCP data path.

V1 is one simulated device per mock instance. Future multi-producer scenarios can be handled by running multiple mock instances on dedicated ports or by adding a separate aggregator design. The binary record keeps `device_id` so a future aggregator can interleave records if needed.

## Configuration

The mock supports a static config file plus CLI overrides.

Expected configurable fields:

- `bind_host`
- `bind_port`
- `consumer_host`
- `consumer_port`
- `device_id`
- `measurement_type`
- `rate_hz`
- `mode`: `rate-controlled` or `burst`
- `ring_buffer_capacity`
- `capture_path`
- `initial_sequence_number`
- GPS latitude, longitude, altitude

CLI overrides should cover common runtime fields such as bind endpoint, consumer endpoint, device ID, rate, mode, buffer capacity, and capture path.

## Capture

When enabled, capture writes the exact packed records sent to the TCP socket into a binary file. The capture format is identical to the TCP stream: repeated fixed-size records.

Capture is disabled by default to avoid affecting high-rate streaming unless explicitly requested.

## Error Handling

Configuration and sample validation errors should fail fast with clear messages.

Runtime handling:

- If the producer cannot connect, it keeps trying and continues buffering according to configured behavior.
- If the ring buffer overflows, oldest records are dropped and counted.
- If the consumer-side socket closes, the producer abandons that connection and retries.
- If the consumer receives malformed or partial data, it closes that producer connection and continues accepting future producers.
- If a socket write fails, the producer rolls back capture bytes for the unsent payload and retries on a later connection.
- If capture writing fails, the producer stops with an explicit error because the captured byte stream would no longer be trustworthy.

## Performance Expectations

At 632 bytes per record and 1000 records per second, the raw stream is about 632,000 bytes per second, approximately 5.1 Mbps before TCP/IP overhead.

Python is not expected to provide hard real-time scheduling. The mock should target average throughput and correct binary output. Burst mode exists to test maximum sustained send/read throughput.

## Testing Strategy

Implementation must use TDD.

Automated tests should cover:

- Struct format size is exactly 632 bytes.
- Pack/unpack roundtrip preserves all fields.
- Golden binary fixture compatibility.
- Sample data validation requires exactly 296 values.
- Measurement type controls how consumers interpret `values`.
- Ring buffer drops oldest records and increments the dropped counter.
- Rate-controlled generator produces monotonic sequence and timestamps.
- Producer connects outward and streams valid records to a listening consumer endpoint.
- Consumer exact-read helper detects partial reads.
- Optional capture output equals the bytes sent over TCP in a controlled test.

Performance testing should be separately runnable so normal tests stay reliable. It should exercise a short high-rate stream at or near 1000 Hz and report achieved records per second and bytes per second.

## Future C Migration

The Python implementation must produce golden binary fixtures that the later C implementation can reproduce exactly.

The C implementation should either:

- use an explicitly packed fixed-width struct with compile-time size checks, or
- serialize fields manually into a byte buffer in the specified little-endian order.

The connector contract is the binary record spec, not Python object names or internal module structure.
