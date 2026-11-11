
"""Convert prepared Aave balances into per-asset scenario USD values."""

from decimal import Decimal, localcontext

import pandas as pd


def value_wallet_reserves(prepared_raw, prices, wallet):
    required = {
        "wallet", "underlying", "symbol", "decimals",
        "atoken_balance_raw", "debt_raw", "collateral_enabled",
    }

    missing = required - set(prepared_raw.columns)
    if missing:
        raise ValueError(f"Missing position fields: {sorted(missing)}")

    selected = prepared_raw[
        prepared_raw["wallet"].str.lower() == wallet.lower()
    ]

    if selected.empty:
        raise ValueError("Wallet not found in prepared positions")

    if selected["underlying"].str.lower().duplicated().any():
        raise ValueError("Duplicate wallet-reserve rows")

    rows = []

    with localcontext() as ctx:
        ctx.prec = 50

        for r in selected.itertuples():
            address = r.underlying.lower()

            if address not in prices:
                raise ValueError(f"Missing Oracle price: {address}")

            price = Decimal(str(prices[address]))
            scale = Decimal(10) ** int(r.decimals)

            if not price.is_finite() or price <= 0:
                raise ValueError(f"Invalid Oracle price: {address}")

            collateral_raw = Decimal(str(r.atoken_balance_raw))
            debt_raw = Decimal(str(r.debt_raw))

            if collateral_raw < 0 or debt_raw < 0:
                raise ValueError("Negative reserve balance")

            collateral_usd = (
                collateral_raw / scale * price
                if r.collateral_enabled else Decimal(0)
            )

            debt_usd = debt_raw / scale * price

            rows.append({
                "wallet": r.wallet,
                "symbol": r.symbol,
                "underlying": address,
                "price_usd": price,
                "collateral_usd": collateral_usd,
                "debt_usd": debt_usd,
            })

    return pd.DataFrame(rows)
