from kc_sensor_mock.ring_buffer import RingBuffer


def test_push_pop_fifo_when_not_full():
    buffer = RingBuffer[int](capacity=3)

    buffer.push(1)
    buffer.push(2)

    assert buffer.pop() == 1
    assert buffer.pop() == 2
    assert buffer.pop() is None
    assert buffer.dropped_total == 0


def test_push_drops_oldest_when_full():
    buffer = RingBuffer[int](capacity=2)

    buffer.push(1)
    buffer.push(2)
    buffer.push(3)

    assert buffer.dropped_total == 1
    assert buffer.pop() == 2
    assert buffer.pop() == 3


def test_capacity_must_be_positive():
    try:
        RingBuffer[int](capacity=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
