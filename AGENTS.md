# Project Overview

This project defines and implements a mock sensor streaming application for an STM-style embedded C device. The initial implementation is Python, but the protocol and architecture must support a later C implementation that behaves like a physical device. The producer connects outbound to a socket opened by the consumer and streams fixed binary records over TCP.

## Scope

The v1 scope is a protocol-first Python mock whose producer connects outbound to a consumer listener, streaming fixed-size little-endian binary sensor records over TCP. The mock generates sample-like spectra or background spectra records, uses a fixed-capacity ring buffer, drops the oldest records on overflow, and optionally captures the exact transmitted bytes to disk.

Out of scope for v1: multi-client fan-out, command/control protocol, dynamic TCP framing headers, record delimiters, per-record checksums, production C implementation, UI, and field metadata in the sensor record.

## Milestones

- Define the binary sensor record contract and golden test vectors.
- Implement Python packing/unpacking for the fixed record.
- Validate and normalize the fixed 296-value sample spectra data before generator work.
- Implement sample-like record generation with configurable rate and burst modes.
- Implement a ring buffer that drops oldest records on overflow.
- Implement the producer as an outbound TCP client that connects to a consumer listener.
- Implement the consumer as an inbound TCP listener that accepts one producer connection at a time.
- Implement CLI entry points: `kc-sensor-producer` (outbound client) and `kc-sensor-consumer` (inbound listener), including config overrides.
- Harden CLI defaults, shutdown behavior, and user-facing error handling, including clean exit on stdin EOF and SIGINT/SIGTERM.
- Add dedicated capture tests that verify the raw capture stream matches the bytes delivered to the TCP consumer endpoint.
- Add automated tests and a separately runnable high-rate performance check.
- Use the protocol spec and golden vectors as the migration path for a later C simulator.
- Keep the manual performance check isolated in `tests/perf/test_stream_rate.py` and run it with `uv run pytest tests/perf/test_stream_rate.py --run-perf -s -v`.

## Specs

Project specs live under `docs/superpowers/specs/`. Relevant specs must be read before planning or implementation work starts.

## Plans

Implementation plans live under `docs/superpowers/plans/`. Relevant plans must be read before implementation work starts.

## Tech Stack

Python is used for the initial mock implementation. Use `uv` for Python project setup, environments, dependency management, and synchronization. The binary protocol must use fixed-width integer fields and explicit little-endian packing so the contract can be reproduced in C.

## Workflow Rules

- Start new project work with brainstorming before implementation.
- Keep this `AGENTS.md` updated when scope, architecture, workflow, tooling, or key constraints change.
- Use TDD for implementation work.
- Testing is required for implementation completion. Run relevant tests or explicitly report why they could not be run.
- For CLI troubleshooting, verify the live socket state with `ss` and `lsof` before treating `Address already in use` as an application bug.
- Keep argparse help output informative enough to show relevant option defaults for operator-facing commands.
- Treat `tests/perf/` as a manual performance lane and keep it excluded from the normal reliability gate by default with the `--run-perf` opt-in.
- Do not add TCP frame headers, record delimiters, or per-record checksums to the default stream; the protocol is repeated fixed-size binary records.
- Treat TCP as the transport-level reliability mechanism. Application-level recovery is reconnect plus `sequence_number` and `dropped_records_total` validation.
- Optimize the protocol for bandwidth and I/O efficiency.
- Treat Python timing at high rates as approximate; validate average throughput and binary correctness.
- Use `bind_host` / `bind_port` for the consumer listener and `consumer_host` / `consumer_port` for the producer target endpoint.

## Roles

- `Embedded Sensor Mock Engineer`: designs and implements protocol-faithful mocks for STM-style sensor data streams, including fixed binary records, buffering, TCP streaming, test vectors, and Python-to-C migration constraints.
