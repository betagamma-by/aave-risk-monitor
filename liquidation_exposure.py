
"""Conservative, pair-specific liquidation exposure estimator.

Amounts are USD values at the same current or stressed price state.
This is not an executable Aave liquidation quote.
"""

from decimal import Decimal, InvalidOperation


def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid numeric input") from None

    if not result.is_finite():
        raise ValueError("Inputs must be finite")
    return result


def estimate_pair_exposure(
    *,
    health_factor,
    debt_asset_usd,
    collateral_asset_usd,
    permitted_repayment_usd,
    liquidation_bonus_pct,
):
    hf = _decimal(health_factor)
    debt = _decimal(debt_asset_usd)
    collateral = _decimal(collateral_asset_usd)
    permitted = _decimal(permitted_repayment_usd)
    bonus = _decimal(liquidation_bonus_pct)

    if any(x < 0 for x in (hf, debt, collateral, permitted, bonus)):
        raise ValueError("Negative inputs are not allowed")

    if hf >= 1 or debt == 0 or collateral == 0:
        repay = Decimal("0")
    else:
        # Cap by selected debt, externally established repayment
        # limit, and available selected collateral.
        repay = min(
            debt,
            permitted,
            collateral / (1 + bonus),
        )

    seized = min(collateral, repay * (1 + bonus))

    return {
        "eligible_by_hf": hf < 1,
        "repayable_debt_usd": repay,
        "collateral_seized_usd": seized,
        "gross_bonus_usd": seized - repay,
        "remaining_debt_asset_usd": debt - repay,
        "remaining_collateral_asset_usd": max(Decimal("0"), collateral - seized),
    }
