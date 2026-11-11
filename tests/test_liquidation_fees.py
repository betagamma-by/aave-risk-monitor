import pytest

from liquidation_fees import estimate_liquidation_fee


def test_protocol_fee_on_bonus_only():
    result = estimate_liquidation_fee(
        repayable_debt_usd=5000,
        gross_collateral_seized_usd=5250,
        protocol_fee_bps=2000,
    )
    assert result["gross_bonus_usd"] == 250
    assert result["protocol_fee_usd"] == 50
    assert result["liquidator_collateral_usd"] == 5200
    assert result["net_bonus_before_costs_usd"] == 200


def test_zero_protocol_fee():
    result = estimate_liquidation_fee(
        repayable_debt_usd=5000,
        gross_collateral_seized_usd=5250,
        protocol_fee_bps=0,
    )
    assert result["protocol_fee_usd"] == 0
    assert result["liquidator_collateral_usd"] == 5250


@pytest.mark.parametrize("bps", [-1, 10001])
def test_invalid_protocol_fee(bps):
    with pytest.raises(ValueError):
        estimate_liquidation_fee(
            repayable_debt_usd=5000,
            gross_collateral_seized_usd=5250,
            protocol_fee_bps=bps,
        )
