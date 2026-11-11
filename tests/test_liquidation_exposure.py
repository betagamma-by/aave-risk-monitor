
from decimal import Decimal

import pytest

from liquidation_exposure import estimate_pair_exposure


def estimate(**overrides):
    inputs = {
        "health_factor": "0.98",
        "debt_asset_usd": "8000",
        "collateral_asset_usd": "10000",
        "permitted_repayment_usd": "4000",
        "liquidation_bonus_pct": "0.05",
    }
    inputs.update(overrides)
    return estimate_pair_exposure(**inputs)


def test_normal_repayment():
    result = estimate()
    assert result["repayable_debt_usd"] == Decimal("4000")
    assert result["collateral_seized_usd"] == Decimal("4200")
    assert result["gross_bonus_usd"] == Decimal("200")


def test_insufficient_collateral():
    result = estimate(collateral_asset_usd="3000")
    assert result["repayable_debt_usd"] == Decimal("3000") / Decimal("1.05")
    assert result["collateral_seized_usd"] == Decimal("3000")
    assert result["remaining_collateral_asset_usd"] == 0


def test_healthy_wallet_cannot_be_liquidated():
    result = estimate(health_factor="1.01")
    assert result["repayable_debt_usd"] == 0
    assert result["collateral_seized_usd"] == 0


def test_repayment_cannot_exceed_selected_debt():
    result = estimate(
        debt_asset_usd="1000",
        permitted_repayment_usd="5000",
    )
    assert result["repayable_debt_usd"] == Decimal("1000")


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        estimate(collateral_asset_usd="-100")


def test_collateral_seizure_never_exceeds_available():
    from liquidation_exposure import estimate_pair_exposure

    collateral = Decimal("599464.605369509903394943")

    result = estimate_pair_exposure(
        health_factor=Decimal("0.20"),
        debt_asset_usd=Decimal("3798612"),
        collateral_asset_usd=collateral,
        permitted_repayment_usd=Decimal("3798612"),
        liquidation_bonus_pct=Decimal("0.075"),
    )

    assert result["repayable_debt_usd"] > 0
    assert result["collateral_seized_usd"] <= collateral
    assert result["remaining_collateral_asset_usd"] >= 0
    assert result["gross_bonus_usd"] >= 0
