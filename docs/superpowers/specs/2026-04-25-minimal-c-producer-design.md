# Minimal C Producer Design

Date: 2026-04-25

## Purpose

Add a minimal C producer that proves wire compatibility with the existing Python consumer.

This work exists to reduce migration risk for a later STM-style embedded implementation. The immediate goal is not feature parity with the Python producer. The immediate goal is a small, deterministic C program that can serialize the existing fixed binary sensor record exactly, verify that output against golden fixtures, and stream those bytes to the current Python consumer without requiring consumer changes.

## Goals

The design must satisfy all of the following:

- Read full sensor records from a CSV file.
- Serialize each record into the existing 632-byte little-endian wire format.
- Prove exact byte compatibility against at least one known golden fixture.
- Connect outbound to the existing Python consumer listener and stream valid records.
- Keep the code structure simple enough to extend later with rate control and reconnect behavior.

## Non-Goals

The first C milestone does not include:

- Ring buffer support.
- Producer-side capture or capture rollback.
- Multithreading or background producer loops.
- Burst mode.
- Generated timestamps or generated sequence numbers in the replay path.
- Multi-client fan-out or listener mode.
- Framing headers, delimiters, or per-record checksums.
- STM HAL integration or non-POSIX transport layers.
- Full feature parity with the Python producer.

## Recommended Approach

Use full-record CSV replay as the first milestone.

Each CSV row contains every field needed for one complete wire record, including all metadata and all 296 sensor values. The C producer parses that row into an in-memory record model and serializes it field-by-field into the established little-endian binary format.

This approach is preferred because it minimizes hidden logic, makes byte-for-byte fixture verification straightforward, and gives the fastest path to a protocol compatibility proof.

## Alternatives Considered

### 1. CSV with generated metadata

Store only the 296 values in CSV and generate timestamps, sequence numbers, and device metadata in C.

This is closer to future embedded behavior, but it weakens deterministic fixture verification and introduces extra logic before the first compatibility milestone.

### 2. Prebuilt binary fixture replay

Pre-convert CSV data into packed binary records and let the C program only send 632-byte chunks.

This is even simpler for transport validation, but it makes CSV less central, reduces human readability, and is a weaker starting point for later embedded producer behavior.

## Architecture

```text
CSV file
  |
  v
CSV parser --> in-memory sensor_record --> explicit LE serializer --> TCP client send
                                          |
                                          +--> fixture byte comparison
```

### Design decisions

#### 1. Manual little-endian serialization

The producer must serialize fields explicitly into a byte buffer rather than relying on packed C struct layout.

Why:

- Wire layout stays compiler-independent.
- Byte order is always explicit.
- Tests can validate each field boundary deterministically.
- Later embedded migration is safer because correctness does not depend on packing pragmas.

#### 2. Linux-first, portability-aware implementation

The first implementation targets a Linux development machine and uses straightforward POSIX sockets and file I/O.

Why:

- This is enough to validate the connector contract now.
- The architecture stays portable because record modeling and serialization remain isolated from the socket layer.

#### 3. Replay-first transport behavior

The first milestone connects, sends CSV-derived records, and exits.

Why:

- This is the smallest possible proof of compatibility.
- Rate control and reconnect logic can be added later without changing the record contract.

## Data Contract

The C implementation uses the existing protocol shape in memory.

```c
#define SENSOR_VALUES_COUNT 296

struct sensor_record {
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
};
```

Important:

- This struct is an in-memory model only.
- On-wire bytes come only from the explicit serializer.
- The binary contract remains the existing 632-byte little-endian record.

## CSV Schema

The CSV file uses a header row and fixed column names.

```text
device_id,measurement_type,sequence_number,dropped_records_total,sensor_timestamp_us,gps_timestamp_us,gps_latitude_e7,gps_longitude_e7,gps_altitude_mm,value_0,...,value_295
```

This produces 305 columns total:

- 9 metadata columns
- 296 value columns

### Validation rules

The parser must fail fast if any of the following occur:

- Header row is missing.
- Header names or order do not match the expected schema.
- Row column count is not exactly 305.
- Integer parsing fails.
- Parsed values overflow the target signed or unsigned field type.
- Any `value_n` field is missing.
- `measurement_type` is not a known supported enum.
- Extra columns are present.

The parser should prefer deterministic rejection over permissive CSV handling.

## Component Boundaries

```text
c/
  include/
    sensor_record.h
    csv_reader.h
    serialize.h
    tcp_client.h
  src/
    main.c
    csv_reader.c
    serialize.c
    tcp_client.c
  tests/
    ...
```

### Responsibilities

- `sensor_record.h`
  - shared constants
  - record type definition
  - protocol size constants
- `csv_reader.c`
  - header validation
  - row parsing
  - integer range checks
- `serialize.c`
  - explicit little-endian writes into a 632-byte output buffer
- `tcp_client.c`
  - connect/send/close behavior for outbound replay
- `main.c`
  - CLI parsing
  - mode dispatch
  - error reporting

This separation keeps parsing, serialization, and networking independently testable.

## Runtime Modes

The minimal CLI should support two modes.

### 1. Emit binary

```text
c-producer --csv path/to/records.csv --emit-binary out.bin
```

Reads CSV rows, serializes them, and writes raw wire-format bytes to a file for fixture comparison.

### 2. Send to consumer

```text
c-producer --csv path/to/records.csv --host 127.0.0.1 --port 9000
```

Connects to the consumer listener, sends serialized records in CSV order, then exits.

### Deferred options

These are intentionally deferred until after replay compatibility is proven:

- `--rate-hz`
- `--reconnect`
- `--loop`

## Error Handling

The C producer should fail fast and print clear operator-facing errors when:

- the CSV file cannot be opened
- the header schema is invalid
- a row cannot be parsed
- a field is out of range
- binary output file creation fails
- socket connection fails
- socket send fails

The first milestone does not need retry loops. A failed send or failed connect ends the program with a non-zero exit code.

## Testing Strategy

### Unit tests

- CSV header validation accepts the expected schema and rejects malformed variants.
- CSV row parsing maps fields into the in-memory record correctly.
- Serializer output length is always exactly 632 bytes.
- Serializer byte layout matches a known golden fixture for at least one CSV row.

### Integration tests

- Binary emit mode produces bytes identical to the golden fixture.
- Python consumer accepts the C producer stream without code changes.
- Decoded records observed by the Python consumer match the CSV input.

### What not to test in v1

- Timing accuracy.
- Reconnect behavior.
- Buffer overflow behavior.
- Concurrent connections.
- Embedded transport integration.

## Success Criteria

The feature is successful when all of the following are true:

- The C producer can read at least one full-record CSV row and serialize it into a 632-byte record.
- The serialized bytes exactly match the expected golden fixture for the same record.
- The existing Python consumer accepts the C producer stream without requiring protocol or consumer changes.
- The implementation remains small and structured so later milestones can add rate control and reconnect behavior without redesigning the serializer or CSV contract.

## Future Extension Path

After the replay milestone is complete, the next logical additions are:

1. Add optional rate-controlled sending.
2. Add reconnect behavior for temporary consumer unavailability.
3. Add an alternate mode where CSV supplies only values and metadata is generated in C.
4. Later replace or wrap the POSIX socket layer for embedded deployment needs.

These extensions should preserve the same wire contract and keep the serializer as the single source of truth for emitted bytes.
