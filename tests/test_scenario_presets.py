from scenario_presets import PRESETS


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