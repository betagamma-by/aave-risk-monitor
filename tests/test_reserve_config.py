
from decimal import Decimal

import pytest

from reserve_config import decode_reserve_configuration


def make_config(
    threshold=8000,
    bonus=10500,
    decimals=18,
    fee=1000,
):
    return (
        (threshold << 16)
        | (bonus << 32)
        | (decimals << 48)
        | (1 << 56)
        | (fee << 152)
    )


def test_decode_liquidation_bonus():
    config = decode_reserve_configuration(make_config())

    assert config["liquidation_bonus_bps"] == 10500
    assert config["liquidation_bonus_pct"] == Decimal("0.05")


def test_decode_protocol_fee():
    config = decode_reserve_configuration(make_config())

    assert config["liquidation_protocol_fee_bps"] == 1000
    assert config["liquidation_protocol_fee_pct"] == Decimal("0.1")


def test_decode_reserve_decimals_and_threshold():
    config = decode_reserve_configuration(
        make_config(threshold=8250, decimals=6)
    )

    assert config["liquidation_threshold_bps"] == 8250
    assert config["decimals"] == 6
    assert config["is_active"] is True


def test_different_liquidation_bonus():
    config = decode_reserve_configuration(
        make_config(bonus=10800)
    )

    assert config["liquidation_bonus_pct"] == Decimal("0.08")


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        decode_reserve_configuration(
            make_config(bonus=9000)
        )


def test_invalid_uint256_rejected():
    with pytest.raises(ValueError):
        decode_reserve_configuration(2**256)

def test_disabled_collateral_configuration():
    config = decode_reserve_configuration(
        make_config(threshold=0, bonus=0)
    )

    assert config["collateral_liquidation_enabled"] is False
    assert config["liquidation_bonus_pct"] == 0