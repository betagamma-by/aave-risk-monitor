
import pandas as pd
import pytest

from data_fetcher import compute_positions


WALLET = "0x1111111111111111111111111111111111111111"
COLLATERAL = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DEBT = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def make_positions(
    collateral=1500,
    debt=1000,
    base_lt_bps=8000,
    emode_lt_bps=0,
    emode_id=0,
):
    """Create deterministic borrower data without blockchain requests."""
    return pd.DataFrame([
        {
            "wallet": WALLET,
            "underlying": COLLATERAL,
            "symbol": "WETH",
            "decimals": 18,
            "atoken_balance_raw": int(collateral * 10**18),
            "debt_raw": 0,
            "collateral_enabled": True,
            "base_lt_bps": base_lt_bps,
            "emode_lt_bps": emode_lt_bps,
            "emode_id": emode_id,
        },
        {
            "wallet": WALLET,
            "underlying": DEBT,
            "symbol": "USDC",
            "decimals": 6,
            "atoken_balance_raw": 0,
            "debt_raw": int(debt * 10**6),
            "collateral_enabled": False,
            "base_lt_bps": 0,
            "emode_lt_bps": 0,
            "emode_id": emode_id,
        },
    ])


PRICES = {COLLATERAL: 1.0, DEBT: 1.0}


def calculate(**kwargs):
    raw = make_positions(**kwargs)
    return compute_positions(raw, PRICES, accrue=False)


def test_health_factor_calculation():
    df, stats = calculate()

    assert len(df) == 1
    assert df.iloc[0]["health_factor"] == pytest.approx(1.2)
    assert df.iloc[0]["collateral_usd"] == 1500
    assert df.iloc[0]["debt_usd"] == 1000
    assert stats["wallets_fetched"] == 1


def test_liquidation_boundary():
    df, _ = calculate(collateral=1200)

    assert df.iloc[0]["health_factor"] == pytest.approx(0.96)
    assert df.iloc[0]["risk_tier"] == "CRITICAL (HF < 1.05)"


def test_emode_liquidation_threshold():
    df, stats = calculate(
        collateral=1500,
        base_lt_bps=8000,
        emode_lt_bps=9300,
        emode_id=1,
    )

    assert df.iloc[0]["health_factor"] == pytest.approx(1.395)
    assert df.iloc[0]["health_factor_base"] == pytest.approx(1.2)
    assert stats["wallets_in_emode"] == 1


def test_missing_debt_price_excludes_wallet():
    raw = make_positions()
    prices = {COLLATERAL: 1.0}

    df, stats = compute_positions(raw, prices, accrue=False)

    assert df.empty
    assert stats["wallets_fetched"] == 1
    assert stats["excluded_unpriced_debt"] == 1
