from liquidation_fees import estimate_liquidation_fee
"""Pair-specific, indicative liquidation exposure under a price scenario."""

from decimal import Decimal

from emode_fetcher import applicable_liquidation_bonus
from liquidation_pair import estimate_liquidation_pair
from position_exposure import value_wallet_reserves
from liquidation_constraints import check_liquidation_dust

def estimate_wallet_liquidation(
    *,
    prepared_raw,
    stressed_prices,
    wallet,
    stressed_hf,
    debt_address,
    collateral_address,
    reserve_configs,
    emode_configs,
):
    hf = Decimal(str(stressed_hf))

    if not hf.is_finite() or hf <= 0 or hf >= 1:
        raise ValueError("Wallet must have a valid stressed HF below 1")

    debt_address = debt_address.lower()
    collateral_address = collateral_address.lower()

    wallet_rows = prepared_raw.loc[
        prepared_raw["wallet"].str.lower() == wallet.lower()
    ]

    if wallet_rows.empty:
        raise ValueError("Wallet not found")

    categories = wallet_rows["emode_id"].dropna().unique()
    if len(categories) != 1:
        raise ValueError("Inconsistent borrower eMode category")

    emode_id = int(categories[0])

    valued = value_wallet_reserves(
        prepared_raw, stressed_prices, wallet
    )

    debt_rows = valued.loc[
        valued["underlying"] == debt_address
    ]
    collateral_rows = valued.loc[
        valued["underlying"] == collateral_address
    ]

    if len(debt_rows) != 1 or len(collateral_rows) != 1:
        raise ValueError("Selected reserve not found or duplicated")

    selected_debt = debt_rows.iloc[0]
    selected_collateral = collateral_rows.iloc[0]

    if selected_debt["debt_usd"] <= 0:
        raise ValueError("Selected reserve has no outstanding debt")

    if selected_collateral["collateral_usd"] <= 0:
        raise ValueError("Selected reserve has no enabled collateral")

    bonus = applicable_liquidation_bonus(
        emode_id,
        collateral_address,
        reserve_configs,
        emode_configs,
    )

    total_debt = sum(
        valued["debt_usd"], Decimal(0)
    )
    total_collateral = sum(
        valued["collateral_usd"], Decimal(0)
    )

    estimate = estimate_liquidation_pair(
        health_factor=hf,
        total_debt_usd=total_debt,
        total_collateral_usd=total_collateral,
        selected_debt_usd=selected_debt["debt_usd"],
        selected_collateral_usd=selected_collateral["collateral_usd"],
        liquidation_bonus_pct=bonus,
    )

    dust_check = check_liquidation_dust(
        remaining_debt_usd=estimate["remaining_debt_asset_usd"],
        remaining_collateral_usd=estimate["remaining_collateral_asset_usd"],
    )

    fee_bps = reserve_configs[collateral_address][
        "liquidation_protocol_fee_bps"
    ]

    fee_result = estimate_liquidation_fee(
        repayable_debt_usd=estimate["repayable_debt_usd"],
        gross_collateral_seized_usd=estimate["collateral_seized_usd"],
        protocol_fee_bps=fee_bps,
    )

    return {
        "wallet": wallet,
        "stressed_hf": hf,
        "emode_id": emode_id,
        "debt_asset": selected_debt["symbol"],
        "collateral_asset": selected_collateral["symbol"],
        "selected_debt_usd": selected_debt["debt_usd"],
        "selected_collateral_usd": selected_collateral["collateral_usd"],
        "total_debt_usd": total_debt,
        "total_collateral_usd": total_collateral,
        "liquidation_bonus_pct": bonus,
        **estimate,
        "protocol_fee_bps": fee_bps,
        "protocol_fee_usd": fee_result["protocol_fee_usd"],
        "liquidator_collateral_usd": fee_result["liquidator_collateral_usd"],
        "net_bonus_before_costs_usd": fee_result["net_bonus_before_costs_usd"],
	**dust_check,
    }
