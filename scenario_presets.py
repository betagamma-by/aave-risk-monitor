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

def resolve_preset(scenario, assets):
    """Convert preset token symbols into contract-address price shocks."""
    if scenario not in PRESETS:
        raise ValueError(f"Unknown scenario: {scenario}")

    changes = {}
    missing = []

    for symbol, pct in PRESETS[scenario].items():
        matching = assets[assets["symbol"] == symbol]

        if matching.empty:
            missing.append(symbol)
            continue

        for address in matching["underlying"]:
            changes[address.lower()] = pct / 100

    return changes, missing