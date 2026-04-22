import pytest

from kc_sensor_mock.protocol import SENSOR_VALUES_COUNT
from kc_sensor_mock.sample_data import SAMPLE_VALUES, validate_values


def test_sample_values_have_required_count():
    assert len(SAMPLE_VALUES) == SENSOR_VALUES_COUNT


def test_sample_values_are_uint16():
    validate_values(SAMPLE_VALUES)


def test_validate_values_rejects_wrong_length():
    with pytest.raises(ValueError, match="296"):
        validate_values([1, 2, 3])


def test_validate_values_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="uint16"):
        validate_values([0] * 295 + [65_536])
