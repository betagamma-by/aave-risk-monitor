
import pytest

from emode_config import collateral_allowed


def test_enabled_reserve():
    assert collateral_allowed(0b1010, 1) is True


def test_disabled_reserve():
    assert collateral_allowed(0b1010, 2) is False


def test_another_enabled_reserve():
    assert collateral_allowed(0b1010, 3) is True


def test_invalid_reserve_id():
    with pytest.raises(ValueError):
        collateral_allowed(0b1010, 128)


def test_invalid_bitmap():
    with pytest.raises(ValueError):
        collateral_allowed(-1, 1)
