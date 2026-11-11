
"""Connect close-factor and collateral-exposure estimates.

All USD values must use the same price scenario.
Indicative only; not an executable liquidation quote.
"""

from close_factor import estimate_repayment_limit
from liquidation_exposure import estimate_pair_exposure


def estimate_liquidation_pair(
    *,
    health_factor,
    total_debt_usd,
    total_collateral_usd,
    selected_debt_usd,
    selected_collateral_usd,
    liquidation_bonus_pct,
):
    # Stage 1: Determine the modeled Aave repayment limit.
    limits = estimate_repayment_limit(
        health_factor=health_factor,
        total_debt_usd=total_debt_usd,
        total_collateral_usd=total_collateral_usd,
        selected_debt_usd=selected_debt_usd,
        selected_collateral_usd=selected_collateral_usd,
    )

    # Stage 2: Apply the available collateral and bonus.
    exposure = estimate_pair_exposure(
        health_factor=health_factor,
        debt_asset_usd=selected_debt_usd,
        collateral_asset_usd=selected_collateral_usd,
        permitted_repayment_usd=limits[
            "selected_debt_repayment_limit_usd"
        ],
        liquidation_bonus_pct=liquidation_bonus_pct,
    )

    return {
        **limits,
        **exposure,
    }
