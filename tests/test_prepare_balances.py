
import pandas as pd
import pytest

import data_fetcher as d


def test_non_gho_balance_preparation():
    """Non-GHO accrual must match the existing calculation."""

    raw = pd.DataFrame([{
        "wallet": "0x1111111111111111111111111111111111111111",
        "underlying": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "symbol": "WETH",
        "decimals": 18,
        "atoken_balance_raw": 10**18,
        "debt_raw": 0,
        "scaled_atoken_raw": 10**18,
        "scaled_vdebt_raw": 0,
        "stable_debt_raw": 0,
        "liq_index": 10**27,
        "borrow_index": 10**27,
        "liq_rate": 0,
        "borrow_rate": 0,
        "reserve_updated_ts": 1700000000,
        "collateral_enabled": True,
        "base_lt_bps": 8000,
        "emode_lt_bps": 0,
        "emode_id": 0,
    }, {
        "wallet": "0x1111111111111111111111111111111111111111",
        "underlying": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "symbol": "USDC",
        "decimals": 6,
        "atoken_balance_raw": 0,
        "debt_raw": 500 * 10**6,
        "scaled_atoken_raw": 0,
        "scaled_vdebt_raw": 500 * 10**6,
        "stable_debt_raw": 0,
        "liq_index": 10**27,
        "borrow_index": 10**27,
        "liq_rate": 0,
        "borrow_rate": 0,
        "reserve_updated_ts": 1700000000,
        "collateral_enabled": False,
        "base_lt_bps": 0,
        "emode_lt_bps": 0,
        "emode_id": 0,
    }])

    prices = {
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 1000,
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": 1,
    }

    timestamp = 1700000100

    prepared = d.prepare_balances(raw, now_ts=timestamp)

    expected_raw = d.add_accrued_balances(raw, now_ts=timestamp)
    expected, _ = d.compute_positions(prepared, prices, accrue=False)

    assert prepared["atoken_balance_raw"].iloc[0] == pytest.approx(
        expected_raw["atoken_now_raw"].iloc[0]
    )
    assert prepared["debt_raw"].iloc[1] == pytest.approx(
        expected_raw["debt_now_raw"].iloc[1]
    )
    assert expected.iloc[0]["health_factor"] == pytest.approx(1.6)


def test_gho_override_is_preserved(monkeypatch):
    """Mock the on-chain GHO override without contacting Ethereum."""

    raw = pd.DataFrame([{
        "symbol": "GHO",
        "atoken_balance_raw": 0,
        "debt_raw": 100,
    }])

    monkeypatch.setattr(
        d,
        "add_accrued_balances",
        lambda raw, now_ts=None: raw.assign(
            atoken_now_raw=0,
            debt_now_raw=100,
        ),
    )

    monkeypatch.setattr(
        d,
        "override_gho_debt",
        lambda raw: raw.assign(debt_now_raw=250),
    )

    prepared = d.prepare_balances(raw)

    assert prepared["debt_raw"].iloc[0] == 250
