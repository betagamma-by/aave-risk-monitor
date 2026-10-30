
import pandas as pd
import pytest
from decimal import Decimal
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
            "atoken_balance_raw": int(Decimal(str(collateral)) * Decimal(10**18)),
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
            "debt_raw": int(Decimal(str(debt)) * Decimal(10**6)),
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

def test_duplicate_wallet_reserve_rows_rejected():
    raw = make_positions()

    # Simulate an upstream data source returning WETH twice.
    raw = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)

    with pytest.raises(
        ValueError,
        match="Duplicate wallet-reserve rows detected"
    ):
        compute_positions(raw, PRICES, accrue=False)

@pytest.mark.parametrize(
    "collateral, expected_hf, expected_tier",
    [
        (1237.5, 0.99, "CRITICAL (HF < 1.05)"),
        (1250, 1.00, "CRITICAL (HF < 1.05)"),
        (1312.5, 1.05, "HIGH (HF 1.05–1.2)"),
        (1500, 1.20, "ELEVATED (HF 1.2–1.5)"),
        (1875, 1.50, "SAFE"),
        (1312.375, 1.049900, "CRITICAL (HF < 1.05)"),
        (1312.45, 1.049960, "CRITICAL (HF < 1.05)"),
        (1312.5125, 1.050010, "HIGH (HF 1.05–1.2)"),
    ],
)
def test_health_factor_boundaries(
    collateral, expected_hf, expected_tier
):
    df, _ = calculate(collateral=collateral)

    assert df.iloc[0]["health_factor"] == pytest.approx(expected_hf)
    assert df.iloc[0]["risk_tier"] == expected_tier

def test_zero_debt_excluded_without_division_error():
    df, stats = calculate(debt=0)

    assert df.empty
    assert stats["wallets_fetched"] == 1
    assert stats["dropped_debt_under_100"] == 1

def test_missing_collateral_price_excludes_wallet():
    raw = make_positions()
    prices = {DEBT: 1.0}

    df, stats = compute_positions(raw, prices, accrue=False)

    assert df.empty
    assert stats["excluded_unpriced_collateral"] == 1
    assert stats["wallets_fetched"] == 1


def test_multiple_collateral_and_debt_assets():
    raw = make_positions(
        collateral=1500,
        debt=1000,
        base_lt_bps=8000,
    )

    extra_collateral = raw.iloc[0].copy()
    extra_collateral["underlying"] = (
        "0xcccccccccccccccccccccccccccccccccccccccc"
    )
    extra_collateral["symbol"] = "WBTC"
    extra_collateral["atoken_balance_raw"] = 500 * 10**18
    extra_collateral["base_lt_bps"] = 7000

    extra_debt = raw.iloc[1].copy()
    extra_debt["underlying"] = (
        "0xdddddddddddddddddddddddddddddddddddddddd"
    )
    extra_debt["symbol"] = "DAI"
    extra_debt["debt_raw"] = 500 * 10**6

    raw = pd.concat(
        [raw, pd.DataFrame([extra_collateral, extra_debt])],
        ignore_index=True,
    )

    prices = {
        **PRICES,
        extra_collateral["underlying"]: 1.0,
        extra_debt["underlying"]: 1.0,
    }

    df, stats = compute_positions(raw, prices, accrue=False)

    assert len(df) == 1
    assert stats["wallets_fetched"] == 1
    assert df.iloc[0]["collateral_usd"] == pytest.approx(2000)
    assert df.iloc[0]["debt_usd"] == pytest.approx(1500)
    assert df.iloc[0]["health_factor"] == pytest.approx(
        (1500 * 0.8 + 500 * 0.7) / 1500
    )
    assert df.iloc[0]["primary_collateral"] == "WETH"
