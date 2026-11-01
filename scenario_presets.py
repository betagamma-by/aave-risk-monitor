"""Illustrative multi-asset price-shock assumptions."""

PRESETS = {
    "ETH Market Crash": {
        "WETH": -30,
        "WBTC": -20,
        "wstETH": -35,
    },
    "Stablecoin Depeg": {
        "USDe": -15,
        "USDC": -5,
    },
    "Staking Token Divergence": {
        "wstETH": -20,
    },
}   