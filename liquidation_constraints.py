"""Indicative Aave V3.3 liquidation dust-rule checks."""

from decimal import Decimal

MIN_LEFTOVER_USD = Decimal("1000")
ROUNDING_TOLERANCE = Decimal("0.00000001")


def check_liquidation_dust(remaining_debt_usd, remaining_collateral_usd):
    debt = Decimal(str(remaining_debt_usd))
    collateral = Decimal(str(remaining_collateral_usd))

    if not all(x.is_finite() for x in (debt, collateral)):
        raise ValueError("Non-finite remaining balance")

    if debt < -ROUNDING_TOLERANCE or collateral < -ROUNDING_TOLERANCE:
        raise ValueError("Invalid negative remaining balance")

    debt = max(Decimal(0), debt)
    collateral = max(Decimal(0), collateral)

    clears_debt = debt <= ROUNDING_TOLERANCE
    clears_collateral = collateral <= ROUNDING_TOLERANCE

    allowed = (
        clears_debt
        or clears_collateral
        or (debt >= MIN_LEFTOVER_USD and collateral >= MIN_LEFTOVER_USD)
    )

    return {
        "passes_dust_check": allowed,
        "clears_selected_debt": clears_debt,
        "clears_selected_collateral": clears_collateral,
        "remaining_debt_usd": debt,
        "remaining_collateral_usd": collateral,
    }
