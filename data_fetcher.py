import requests
import pandas as pd

SUBGRAPH_URL = "https://api.studio.thegraph.com/query/1756180/aave-v-3-risk-monitor/v0.0.1"

SYMBOL_TO_COINGECKO_ID = {
    "WETH": "ethereum", "WBTC": "wrapped-bitcoin", "USDC": "usd-coin",
    "USDT": "tether", "DAI": "dai", "GHO": "gho", "USDe": "ethena-usde",
    "wstETH": "wrapped-steth", "cbBTC": "coinbase-wrapped-btc",
    "USDS": "usds", "PYUSD": "paypal-usd", "sUSDe": "ethena-staked-usde",
    "EURC": "euro-coin", "RLUSD": "ripple-usd", "USDtb": "usdtb",
    # Newly added
    "LINK": "chainlink", "MKR": "maker", "AAVE": "aave", "CRV": "curve-dao-token",
    "UNI": "uniswap", "BAL": "balancer", "LDO": "lido-dao", "ENS": "ethereum-name-service",
    "rETH": "rocket-pool-eth", "weETH": "wrapped-eeth", "ETHx": "stader-ethx",
    "LBTC": "lombard-staked-btc", "tBTC": "tbtc", "FBTC": "ignition-fbtc",
    "FRAX": "frax", "crvUSD": "crvusd", "LUSD": "liquity-usd", "XAUt": "tether-gold",
}

def is_pendle_pt_token(symbol: str) -> bool:
    """Pendle Principal Tokens require per-maturity pricing we don't support — exclude explicitly."""
    return symbol.startswith("PT-")

def fetch_live_prices(symbols: set) -> dict:
    ids = [SYMBOL_TO_COINGECKO_ID.get(s) for s in symbols if s in SYMBOL_TO_COINGECKO_ID]
    ids = [i for i in ids if i]
    if not ids:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": "usd"}
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()
    id_to_symbol = {v: k for k, v in SYMBOL_TO_COINGECKO_ID.items()}
    return {id_to_symbol[cg_id]: info["usd"] for cg_id, info in data.items() if cg_id in id_to_symbol}


def fetch_high_risk_positions(top_reserves=5, borrowers_per_reserve=15):
    reserves_query = """
    { reserves(first: %d, orderBy: totalCurrentVariableDebt, orderDirection: desc) { id symbol } }
    """ % top_reserves
    resp = requests.post(SUBGRAPH_URL, json={"query": reserves_query}, timeout=30)
    reserves_data = resp.json().get("data", {}).get("reserves", [])
    if not reserves_data:
        raise ValueError("No reserves found")

    unique_wallets = set()
    for reserve in reserves_data:
        discovery_query = """
        { userReserves(first: %d, orderBy: currentTotalDebt, orderDirection: desc,
            where: { reserve: "%s", currentTotalDebt_gt: "0" }) { user { id } } }
        """ % (borrowers_per_reserve, reserve["id"])
        resp = requests.post(SUBGRAPH_URL, json={"query": discovery_query}, timeout=30)
        for ur in resp.json().get("data", {}).get("userReserves", []):
            unique_wallets.add(ur["user"]["id"])

    if not unique_wallets:
        return pd.DataFrame()

    wallets_filter = str(list(unique_wallets)).replace("'", '"')
    detail_query = """
    { users(where: { id_in: %s }) { id reserves {
        currentATokenBalance currentTotalDebt usageAsCollateralEnabledOnUser
        reserve { symbol decimals reserveLiquidationThreshold } } } }
    """ % wallets_filter
    resp = requests.post(SUBGRAPH_URL, json={"query": detail_query}, timeout=30)
    users = resp.json().get("data", {}).get("users", [])

    all_symbols = {r["reserve"]["symbol"] for u in users for r in u.get("reserves", [])}
    tradeable_symbols = {s for s in all_symbols if not is_pendle_pt_token(s)}
    live_prices = fetch_live_prices(tradeable_symbols)

    missing = tradeable_symbols - set(live_prices.keys())
    pt_symbols = all_symbols - tradeable_symbols
    if missing:
        print(f"⚠️ No price found for (non-PT): {missing}")
    if pt_symbols:
        print(f"ℹ️ Excluded Pendle PT collateral (unsupported pricing): {pt_symbols}")

    rows = []
    excluded_wallets = 0

    for u in users:
        collateral_usd = 0.0
        debt_usd = 0.0
        weighted_threshold_sum = 0.0
        primary_collateral = None
        max_collateral_val = 0.0
        has_unpriced_collateral = False

        for r in u.get("reserves", []):
            symbol = r["reserve"]["symbol"]
            decimals = r["reserve"]["decimals"]
            liq_threshold = float(r["reserve"]["reserveLiquidationThreshold"]) / 10000

            if is_pendle_pt_token(symbol):
                if r["usageAsCollateralEnabledOnUser"] and float(r["currentATokenBalance"]) > 0:
                    has_unpriced_collateral = True
                continue

            price_usd = live_prices.get(symbol, 0)
            if price_usd == 0:
                if r["usageAsCollateralEnabledOnUser"] and float(r["currentATokenBalance"]) > 0:
                    has_unpriced_collateral = True
                continue

            if r["usageAsCollateralEnabledOnUser"]:
                balance = float(r["currentATokenBalance"]) / (10 ** decimals)
                val = balance * price_usd
                collateral_usd += val
                weighted_threshold_sum += val * liq_threshold
                if val > max_collateral_val:
                    max_collateral_val = val
                    primary_collateral = symbol

            debt_balance = float(r["currentTotalDebt"]) / (10 ** decimals)
            debt_usd += debt_balance * price_usd

        if has_unpriced_collateral:
            excluded_wallets += 1
            continue  # exclude wallets whose collateral we can't accurately price

        if debt_usd < 100:
            continue

        avg_liq_threshold = weighted_threshold_sum / collateral_usd if collateral_usd > 0 else 0
        health_factor = (collateral_usd * avg_liq_threshold) / debt_usd if debt_usd > 0 else 999

        rows.append({
            "wallet": u["id"][:10] + "...",
            "wallet_full": u["id"],
            "collateral_usd": round(collateral_usd, 2),
            "debt_usd": round(debt_usd, 2),
            "health_factor": round(health_factor, 4),
            "primary_collateral": primary_collateral or "Unknown",
            "risk_tier": (
                "CRITICAL (HF < 1.05)" if health_factor < 1.05
                else "HIGH (HF 1.05–1.2)" if health_factor < 1.2
                else "ELEVATED (HF 1.2–1.5)" if health_factor < 1.5
                else "SAFE"
            )
        })

    if excluded_wallets:
        print(f"ℹ️ Excluded {excluded_wallets} wallet(s) with unpriceable collateral (e.g. Pendle PT positions)")

    df = pd.DataFrame(rows)
    return df.sort_values("health_factor").head(75) if not df.empty else df