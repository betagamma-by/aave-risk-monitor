import pandas as pd

from scenario_presets import resolve_preset, PRESETS

def test_eth_crash_assumptions():
    assert PRESETS["ETH Market Crash"] == {
        "WETH": -30,
        "WBTC": -20,
        "wstETH": -35,
    }


def test_stablecoin_depeg_assumptions():
    assert PRESETS["Stablecoin Depeg"] == {
        "USDe": -15,
        "USDC": -5,
    }


def test_staking_divergence_assumptions():
    assert PRESETS["Staking Token Divergence"] == {
        "wstETH": -20,
    }

def test_preset_maps_symbols_to_correct_addresses():
    assets = pd.DataFrame([
        {"symbol": "WETH", "underlying": "0xaaa"},
        {"symbol": "WBTC", "underlying": "0xbbb"},
        {"symbol": "wstETH", "underlying": "0xccc"},
    ])

    changes, missing = resolve_preset("ETH Market Crash", assets)

    assert changes == {
        "0xaaa": -0.30,
        "0xbbb": -0.20,
        "0xccc": -0.35,
    }
    assert missing == []

def test_missing_preset_asset_is_reported():
    assets = pd.DataFrame([
        {"symbol": "WETH", "underlying": "0xaaa"},
    ])

    changes, missing = resolve_preset("ETH Market Crash", assets)

    assert changes == {"0xaaa": -0.30}
    assert missing == ["WBTC", "wstETH"]