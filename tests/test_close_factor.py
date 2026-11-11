
from decimal import Decimal

import pytest

from close_factor import estimate_repayment_limit

def calculate(
    hf, debt=8000, collateral=10000,
    selected=8000, selected_collateral=10000,
):
    return estimate_repayment_limit(
        health_factor=hf,
        total_debt_usd=debt,
        total_collateral_usd=collateral,
        selected_debt_usd=selected,
        selected_collateral_usd=selected_collateral,
    )

def test_healthy_position():
    result = calculate("1.01")
    assert result["close_factor"] == 0
    assert result["selected_debt_repayment_limit_usd"] == 0


def test_partial_liquidation():
    result = calculate("0.98")
    assert result["close_factor"] == Decimal("0.5")
    assert result["selected_debt_repayment_limit_usd"] == 4000


def test_severe_liquidation():
    result = calculate("0.90")
    assert result["close_factor"] == 1
    assert result["selected_debt_repayment_limit_usd"] == 8000


def test_small_position():
    result = calculate(
        "0.98",
        debt=1500,
        collateral=1800,
        selected=1500,
        selected_collateral=1800,
    )
    assert result["close_factor"] == 1


def test_multiple_debt_assets():
    result = calculate("0.98", debt=9000, selected=3000)
    assert result["position_repayment_limit_usd"] == 4500
    assert result["selected_debt_repayment_limit_usd"] == 3000


def test_invalid_selected_debt():
    with pytest.raises(ValueError):
        calculate("0.98", debt=1000, selected=2000)

def test_small_selected_debt_triggers_full_close_factor():
    result = calculate("0.98", debt=10000, selected=1500)
    assert result["close_factor"] == 1
    assert result["selected_debt_repayment_limit_usd"] == 1500


def test_small_selected_collateral_triggers_full_close_factor():
    result = calculate(
        "0.98",
        collateral=12000,
        selected_collateral=1500,
    )
    assert result["close_factor"] == 1


def test_exact_hf_threshold():
    result = calculate("0.95")
    assert result["close_factor"] == 1