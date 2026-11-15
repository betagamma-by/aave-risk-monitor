import pytest

from exposure_access import exposure_available


@pytest.mark.parametrize(
    "source,inputs,block,verified,expected",
    [
        ("live", True, 12345, True, True),
        ("snapshot", True, 12345, True, False),
        ("live", False, 12345, True, False),
        ("live", True, None, True, False),
        ("live", True, 12345, False, False),
        ("live", True, True, True, False),
    ],
)
def test_exposure_access(
    source, inputs, block, verified, expected
):
    assert exposure_available(
        source, inputs, block, verified
    ) is expected
