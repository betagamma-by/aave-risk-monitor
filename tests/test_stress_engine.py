
from decimal import Decimal

import pandas as pd
import pytest

from stress_engine import simulate_price_shock


WETH = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
USDC = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
WALLET = "0x1111111111111111111111111111111111111111"


def raw_position(collateral_asset=WETH, debt_asset=USDC):
    rows = []
    for address, symbol, decimals in [
        (WETH, "WETH", 18),
        (USDC, "USDC", 6),
    ]:
        scale = Decimal(10) ** decimals
        rows.append({
            "wallet": WALLET,
            "underlying": address,
            "symbol": symbol,
            "decimals": decimals,
            "atoken_balance_raw": int(Decimal(1500) * scale)
            if address == collateral_asset else 0,
            "debt_raw": int(Decimal(1000) * scale)
            if address == debt_asset else 0,
            "collateral_enabled": address == collateral_asset,
            "base_lt_bps": 8000 if address == collateral_asset else 0,
            "emode_lt_bps": 0,
            "emode_id": 0,
        })
    return pd.DataFrame(rows)


def test_eth_collateral_crash():
    raw = raw_position()
    result = simulate_price_shock(
        raw, {WETH: 1, USDC: 1}, {WETH: -0.20}
    )
    row = result.iloc[0]

    assert row["baseline_hf"] == pytest.approx(1.2)
    assert row["stressed_hf"] == pytest.approx(0.96)
    assert bool(row["newly_liquidatable"])


def test_eth_debt_becomes_cheaper():
    raw = raw_position(
        collateral_asset=USDC,
        debt_asset=WETH,
    )
    result = simulate_price_shock(
        raw, {WETH: 1, USDC: 1}, {WETH: -0.20}
    )
    row = result.iloc[0]

    assert row["baseline_hf"] == pytest.approx(1.2)
    assert row["stressed_hf"] == pytest.approx(1.5)
    assert not bool(row["newly_liquidatable"])


def test_unchanged_prices():
    raw = raw_position()
    prices = {WETH: 1, USDC: 1}

    result = simulate_price_shock(raw, prices, {})

    assert result.iloc[0]["baseline_hf"] == pytest.approx(
        result.iloc[0]["stressed_hf"]
    )
    assert prices == {WETH: 1, USDC: 1}

def test_affected_wallet_when_eth_price_changes():
    raw = raw_position()

    result = simulate_price_shock(
        raw,
        {WETH: 1, USDC: 1},
        {WETH: -0.20},
    )

    assert bool(result.iloc[0]["affected_by_shock"])

def test_unaffected_wallet_when_price_unchanged():
    raw = raw_position()

    result = simulate_price_shock(
        raw,
        {WETH: 1, USDC: 1},
        {},
    )

    assert not bool(result.iloc[0]["affected_by_shock"])


def test_stablecoin_depeg():
    raw = raw_position()

    result = simulate_price_shock(
        raw,
        {WETH: 1, USDC: 1},
        {USDC: -0.10},
    )

    # USDC is borrowed: its depeg reduces USD debt.
    assert result.iloc[0]["baseline_hf"] == pytest.approx(1.2)
    assert result.iloc[0]["stressed_hf"] == pytest.approx(1.2 / 0.9)


def test_staking_token_divergence():
    wsteth = "0xcccccccccccccccccccccccccccccccccccccccc"
    raw = raw_position()
    raw.loc[raw["underlying"] == WETH, "underlying"] = wsteth
    raw.loc[raw["symbol"] == "WETH", "symbol"] = "wstETH"

    result = simulate_price_shock(
        raw,
        {wsteth: 1, USDC: 1},
        {wsteth: -0.15},
    )

    # A wstETH-specific decline, leaving USDC unchanged.
    assert result.iloc[0]["stressed_hf"] == pytest.approx(1.02)

def test_multiple_asset_shocks():
    raw = raw_position()

    result = simulate_price_shock(
        raw,
        {WETH: 1, USDC: 1},
        {WETH: -0.20, USDC: -0.10},
    )

    # Collateral declines 20%; borrowed USDC declines 10%.
    assert result.iloc[0]["stressed_hf"] == pytest.approx(
        1.2 * 0.8 / 0.9
    )

def test_invalid_price_shock_rejected():
    raw = raw_position()

    with pytest.raises(ValueError):
        simulate_price_shock(
            raw,
            {WETH: 1, USDC: 1},
            {WETH: -1.0},
        )

def test_stressed_debt_below_100_is_retained():
    raw = raw_position()

    # Reduce baseline debt to $105.
    raw.loc[raw["underlying"] == USDC, "debt_raw"] = 105 * 10**6

    result = simulate_price_shock(
        raw,
        {WETH: 1, USDC: 1},
        {USDC: -0.20},
    )

    assert len(result) == 1
    assert result.iloc[0]["baseline_debt_usd"] == pytest.approx(105)
    assert result.iloc[0]["stressed_debt_usd"] == pytest.approx(84)


def test_zero_debt_excluded_with_zero_minimum():
    from data_fetcher import compute_positions

    raw = raw_position()
    raw["debt_raw"] = 0

    positions, _ = compute_positions(
        raw,
        {WETH: 1, USDC: 1},
        accrue=False,
        min_debt_usd=0,
    )

    assert positions.empty