
"""Indicative Aave V3.3-style close-factor estimate.

Not an executable liquidation quote. Dust rules and transaction
constraints are not modeled. Verify deployed Pool implementation.
"""

from decimal import Decimal, InvalidOperation


def _amount(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid numeric input") from None

    if not number.is_finite() or number < 0:
        raise ValueError("Inputs must be finite and nonnegative")

    return number


def estimate_repayment_limit(
    *,
    health_factor,
    total_debt_usd,
    total_collateral_usd,
    selected_debt_usd,
    selected_collateral_usd,
):
    hf = _amount(health_factor)
    debt = _amount(total_debt_usd)
    collateral = _amount(total_collateral_usd)
    selected_debt = _amount(selected_debt_usd)
    selected_collateral = _amount(selected_collateral_usd)

    if selected_debt > debt:
        raise ValueError("Selected debt exceeds total debt")
    if selected_collateral > collateral:
        raise ValueError("Selected collateral exceeds total collateral")

    if hf >= 1 or debt == 0 or selected_debt == 0:
        factor = Decimal("0")
    elif (
        hf <= Decimal("0.95")
        or selected_debt < Decimal("2000")
        or selected_collateral < Decimal("2000")
    ):
        factor = Decimal("1")
    else:
        factor = Decimal("0.5")

    position_limit = debt * factor
    selected_limit = min(selected_debt, position_limit)

    return {
        "close_factor": factor,
        "position_repayment_limit_usd": position_limit,
        "selected_debt_repayment_limit_usd": selected_limit,
    }
