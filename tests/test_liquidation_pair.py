
from decimal import Decimal

import pytest

from liquidation_pair import estimate_liquidation_pair


def calculate(**overrides):
    inputs = {
        "health_factor": "0.98",
        "total_debt_usd": "8000",
        "total_collateral_usd": "10000",
        "selected_debt_usd": "8000",
        "selected_collateral_usd": "3000",
        "liquidation_bonus_pct": "0.05",
    }
    inputs.update(overrides)
    return estimate_liquidation_pair(**inputs)


def test_collateral_limits_repayment():
    result = calculate()

    assert result["close_factor"] == Decimal("0.5")
    assert result["position_repayment_limit_usd"] == 4000
    assert result["repayable_debt_usd"] == (
        Decimal("3000") / Decimal("1.05")
    )
    assert result["collateral_seized_usd"] == 3000


def test_small_selected_collateral_changes_close_factor():
    result = calculate(selected_collateral_usd="1500")

    assert result["close_factor"] == 1
    assert result["repayable_debt_usd"] == (
        Decimal("1500") / Decimal("1.05")
    )


def test_healthy_wallet_has_zero_exposure():
    result = calculate(health_factor="1.10")

    assert result["close_factor"] == 0
    assert result["repayable_debt_usd"] == 0
    assert result["collateral_seized_usd"] == 0


def test_selected_collateral_cannot_exceed_total():
    with pytest.raises(ValueError):
        calculate(selected_collateral_usd="11000")
