# Project Overview

This project defines and implements a mock sensor streaming application for an STM-style embedded C device. The initial implementation will be Python, but the protocol and architecture must support a later C implementation that behaves like a physical device producing fixed binary records over TCP.

## Scope

The v1 scope is a protocol-first Python mock that streams fixed-size little-endian binary sensor records over TCP to one connected consumer at a time. The mock will generate sample-like spectra or background spectra records, use a fixed-capacity ring buffer, drop the oldest records on overflow, and optionally capture the exact transmitted bytes to disk.

Out of scope for v1: multi-client fan-out, command/control protocol, dynamic TCP framing headers, record delimiters, per-record checksums, production C implementation, UI, and field metadata in the sensor record.

## Milestones

- Define the binary sensor record contract and golden test vectors.
- Implement Python packing/unpacking for the fixed record.
- Validate and normalize the fixed 296-value sample spectra data before generator work.
- Implement sample-like record generation with configurable rate and burst modes.
- Implement a drop-oldest ring buffer.
- Implement single-client TCP streaming.
- Implement CLI entry points for server and client invocation, including config overrides.
- Harden CLI defaults, shutdown behavior, and user-facing error handling, including clean server exit on stdin EOF and SIGINT/SIGTERM.
- Implement a reference client for connector validation.
- Add dedicated capture tests that verify the raw capture stream matches the bytes delivered to the TCP client.
- Add automated tests and a separately runnable high-rate performance check.
- Use the protocol spec and golden vectors as the migration path for a later C simulator.

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
- Do not add TCP frame headers, record delimiters, or per-record checksums to the default stream; the protocol is repeated fixed-size binary records.
- Treat TCP as the transport-level reliability mechanism. Application-level recovery is reconnect plus `sequence_number` and `dropped_records_total` validation.
- Optimize the protocol for bandwidth and I/O efficiency.
- Treat Python timing at high rates as approximate; validate average throughput and binary correctness.

## Roles

- `Embedded Sensor Mock Engineer`: designs and implements protocol-faithful mocks for STM-style sensor data streams, including fixed binary records, buffering, TCP streaming, test vectors, and Python-to-C migration constraints.
