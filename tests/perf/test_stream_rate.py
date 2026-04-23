"""Manual perf lane for reversed producer/consumer transport."""

from __future__ import annotations

import socket
import time
from time import perf_counter

import pytest

from kc_sensor_mock.config import MockConfig
from kc_sensor_mock.protocol import MEASUREMENT_TYPE_SPECTRA, RECORD_SIZE


@pytest.mark.perf
def test_stream_rate() -> None:
    count = 1_000

    # Perf lane: raw listening socket acts as the consumer endpoint so the test
    # controls the read side and measures true throughput.  The producer connects
    # to it second (consumer-first / producer-second).
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_sock.bind(("127.0.0.1", 0))
    listen_sock.listen(1)
    listen_host, listen_port = listen_sock.getsockname()
    listen_sock.settimeout(0.2)

    producer_config = MockConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        consumer_host=listen_host,
        consumer_port=listen_port,
        device_id=1,
        measurement_type=MEASUREMENT_TYPE_SPECTRA,
        rate_hz=1_000,
        mode="burst",
        ring_buffer_capacity=2_048,
        initial_sequence_number=0,
        gps_latitude=56.6718316,
        gps_longitude=24.2391946,
        gps_altitude_m=35.0,
        capture_path=None,
    )

    producer_client = producer.SensorProducerClient(producer_config)
    producer_client.start()

    # Accept the producer's connection on the raw listener.
    client_sock, _ = listen_sock.accept()
    client_sock.settimeout(10.0)

    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        """Read exactly *size* bytes, handling partial TCP chunks."""
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("socket closed before reading full record")
            data.extend(chunk)
        return bytes(data)

    record_count = 0
    started = perf_counter()
    try:
        while record_count < count:
            _recv_exact(client_sock, RECORD_SIZE)
            record_count += 1
    except socket.timeout:
        pass
    finally:
        producer_client.stop()
        client_sock.close()
        listen_sock.close()

    elapsed = perf_counter() - started
    assert record_count == count

    records_per_second = count / elapsed
    bytes_per_second = (count * RECORD_SIZE) / elapsed
    print(
        f"read {count} records in {elapsed:.3f}s "
        f"({records_per_second:.1f} records/s, {bytes_per_second:.1f} bytes/s)"
    )


import kc_sensor_mock.producer as producer  # noqa: E402
