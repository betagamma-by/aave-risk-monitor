
from decimal import Decimal

import pandas as pd
import pytest

from position_exposure import value_wallet_reserves


def sample_position():
    return pd.DataFrame([
        {
            "wallet": "0xalice",
            "symbol": "WETH",
            "underlying": "0xaaa",
            "decimals": 18,
            "atoken_balance_raw": str(2 * 10**18),
            "debt_raw": "0",
            "collateral_enabled": True,
        },
        {
            "wallet": "0xalice",
            "symbol": "USDC",
            "underlying": "0xbbb",
            "decimals": 6,
            "atoken_balance_raw": "0",
            "debt_raw": str(3000 * 10**6),
            "collateral_enabled": False,
        },
    ])


def test_reserve_values_use_provided_prices():
    result = value_wallet_reserves(
        sample_position(),
        {"0xaaa": 2000, "0xbbb": 1},
        "0xalice",
    )
    assert result["collateral_usd"].sum() == Decimal("4000")
    assert result["debt_usd"].sum() == Decimal("3000")


def test_stressed_prices_revalue_collateral():
    result = value_wallet_reserves(
        sample_position(),
        {"0xaaa": 1400, "0xbbb": 1},
        "0xalice",
    )
    assert result["collateral_usd"].sum() == Decimal("2800")
    assert result["debt_usd"].sum() == Decimal("3000")


def test_missing_price_rejected():
    with pytest.raises(ValueError, match="Missing Oracle price"):
        value_wallet_reserves(
            sample_position(),
            {"0xaaa": 2000},
            "0xalice",
        )


def test_duplicate_reserve_rejected():
    raw = pd.concat(
        [sample_position(), sample_position().iloc[[0]]],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="Duplicate"):
        value_wallet_reserves(
            raw,
            {"0xaaa": 2000, "0xbbb": 1},
            "0xalice",
        )
