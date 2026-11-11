"""Asset-specific price shocks using prepared borrower balances."""

from decimal import Decimal, localcontext
from data_fetcher import compute_positions

def simulate_price_shock(prepared_raw, prices, shocks, return_prices=False):
    """
    prepared_raw: balances already adjusted for accrual/GHO,
                  stored in atoken_balance_raw and debt_raw.
    prices: {underlying_address: USD price}
    shocks: {underlying_address: fractional change}
            Example: -0.30 means a 30% price drop.
    """
    with localcontext() as ctx:
        ctx.prec = 50

        stressed_prices = dict(prices)

        for address, change in shocks.items():
            address = address.lower()

            if address not in stressed_prices:
                raise ValueError(f"No baseline price for {address}")

            change = Decimal(str(change))
            if not change.is_finite() or change <= -1:
                raise ValueError("Shock must be finite and greater than -100%")

            baseline_price = Decimal(str(stressed_prices[address]))
            stressed_prices[address] = float(
                baseline_price * (Decimal(1) + change)
            )

    baseline, _ = compute_positions(
        prepared_raw.copy(), prices, accrue=False
    )
    stressed, _ = compute_positions(
        prepared_raw.copy(),
        stressed_prices,
        accrue=False,
        min_debt_usd=0,
    )

    if set(baseline["wallet_full"]) != set(stressed["wallet_full"]):
        raise ValueError(
            "Scenario changed the analyzed wallet population; "
            "review debt thresholds or missing prices."
        )

    result = baseline[
        ["wallet_full", "health_factor", "debt_usd"]
    ].rename(columns={
        "health_factor": "baseline_hf",
        "debt_usd": "baseline_debt_usd",
    }).merge(
        stressed[
            ["wallet_full", "health_factor", "debt_usd"]
        ].rename(columns={
            "health_factor": "stressed_hf",
            "debt_usd": "stressed_debt_usd",
        }),
        on="wallet_full",
        validate="one_to_one",
    )

    result["hf_change"] = (
        result["stressed_hf"] - result["baseline_hf"]
    )

    result["hf_change_pct"] = (
        result["hf_change"] / result["baseline_hf"] * 100
    )

    result["hf_change"] = result["stressed_hf"] - result["baseline_hf"]

    result["affected_by_shock"] = (
        result["hf_change"].abs() > 1e-9
    )
    result["already_liquidatable"] = result["baseline_hf"] < 1.0
    result["newly_liquidatable"] = (
        (result["baseline_hf"] >= 1.0)
        & (result["stressed_hf"] < 1.0)
    )

    if return_prices:
        return result, stressed_prices

    return result