import requests
import pandas as pd
import time 

SUBGRAPH_URL = "https://api.studio.thegraph.com/query/1756180/aave-v-3-risk-monitor/v0.0.2"

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

def _gql(query: str) -> dict:
    resp = requests.post(SUBGRAPH_URL, json={"query": query}, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        raise RuntimeError(f"Subgraph error: {body['errors']}")
    return body["data"]


def fetch_live_prices(symbols: set) -> dict:
    ids = [SYMBOL_TO_COINGECKO_ID.get(s) for s in symbols if s in SYMBOL_TO_COINGECKO_ID]
    ids = [i for i in ids if i]
    if not ids:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": "usd"}
    for attempt in range(3):
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            break
        time.sleep(5 * (attempt + 1))  # rate-limited or error: wait, then retry
    else:
        raise RuntimeError(f"CoinGecko failed, last status {resp.status_code}")
    id_to_symbol = {v: k for k, v in SYMBOL_TO_COINGECKO_ID.items()}
    return {id_to_symbol[cg_id]: info["usd"] for cg_id, info in data.items() if cg_id in id_to_symbol}


def fetch_raw_positions(top_reserves=5, borrowers_per_reserve=15):
    """One row per wallet-reserve, raw values kept as the subgraph returns them."""
    reserves = _gql(
        "{ reserves(first: %d, orderBy: totalCurrentVariableDebt, orderDirection: desc) { id symbol } }"
        % top_reserves
    )["reserves"]
    if not reserves:
        raise ValueError("No reserves found")

    wallets = set()
    for r in reserves:
        d = _gql(
            """{ userReserves(first: %d, orderBy: currentTotalDebt, orderDirection: desc,
                where: { reserve: "%s", currentTotalDebt_gt: "0" }) { user { id } } }"""
            % (borrowers_per_reserve, r["id"])
        )
        wallets |= {ur["user"]["id"] for ur in d["userReserves"]}
    if not wallets:
        return pd.DataFrame()

    wallets_filter = str(sorted(wallets)).replace("'", '"')
    users = _gql(
        """{ users(where: { id_in: %s }) {
            id
            eModeCategoryId { id liquidationThreshold assets { asset collateral } }
            reserves { currentATokenBalance currentTotalDebt usageAsCollateralEnabledOnUser
                reserve { symbol decimals reserveLiquidationThreshold underlyingAsset } } } }"""
        % wallets_filter
    )["users"]

    rows = []
    for u in users:
        cat = u.get("eModeCategoryId")
        cat_id = int(cat["id"]) if cat else 0
        cat_lt = int(cat["liquidationThreshold"]) if cat else 0
        cat_collateral = {a["asset"].lower() for a in cat["assets"] if a["collateral"]} if cat else set()
        for r in u.get("reserves", []):
            res = r["reserve"]
            in_category = res["underlyingAsset"].lower() in cat_collateral
            rows.append({
                "wallet": u["id"],
                "symbol": res["symbol"],
                "underlying": res["underlyingAsset"].lower(),
                "decimals": int(res["decimals"]),
                "base_lt_bps": int(res["reserveLiquidationThreshold"]),
                "atoken_balance_raw": r["currentATokenBalance"],  # strings: values can be huge
                "debt_raw": r["currentTotalDebt"],
                "collateral_enabled": bool(r["usageAsCollateralEnabledOnUser"]),
                "emode_id": cat_id,
                "emode_lt_bps": cat_lt if in_category else 0,  # 0 = no eMode boost for this asset
            })
    return pd.DataFrame(rows)


def compute_positions(raw, prices):
    stats = {"wallets_fetched": 0, "wallets_in_emode": 0, "excluded_unpriced_collateral": 0,
             "wallets_with_ignored_debt": 0, "dropped_debt_under_100": 0}
    if raw.empty:
        return pd.DataFrame(), stats
    stats["wallets_fetched"] = int(raw["wallet"].nunique())
    stats["wallets_in_emode"] = int((raw.groupby("wallet")["emode_id"].max() > 0).sum())

    rows = []
    for wallet, g in raw.groupby("wallet"):
        collateral_usd = debt_usd = weighted = weighted_base = max_val = 0.0
        primary, unpriced_collateral, ignored_debt = None, False, False

        for r in g.itertuples():
            balance_raw, debt_raw = float(r.atoken_balance_raw), float(r.debt_raw)
            price = 0 if is_pendle_pt_token(r.symbol) else prices.get(r.symbol, 0)
            if price == 0:
                if r.collateral_enabled and balance_raw > 0:
                    unpriced_collateral = True
                if debt_raw > 0:
                    ignored_debt = True  # diagnostic: this debt is counted as $0 (fix F4 later)
                continue
            if r.collateral_enabled:
                val = balance_raw / 10 ** r.decimals * price
                collateral_usd += val
                weighted_base += val * r.base_lt_bps / 10000
                weighted += val * (r.emode_lt_bps or r.base_lt_bps) / 10000
                if val > max_val:
                    max_val, primary = val, r.symbol
            debt_usd += debt_raw / 10 ** r.decimals * price

        if unpriced_collateral:
            stats["excluded_unpriced_collateral"] += 1
            continue
        if ignored_debt:
            stats["wallets_with_ignored_debt"] += 1
        if debt_usd < 100:
            stats["dropped_debt_under_100"] += 1
            continue

        hf = weighted / debt_usd
        hf_base = weighted_base / debt_usd  # old logic: base thresholds only
        rows.append({
            "wallet": wallet[:10] + "...",
            "wallet_full": wallet,
            "collateral_usd": round(collateral_usd, 2),
            "debt_usd": round(debt_usd, 2),
            "health_factor": round(hf, 4),
            "health_factor_base": round(hf_base, 4),
            "emode_id": int(g["emode_id"].iloc[0]),
            "primary_collateral": primary or "Unknown",
            "risk_tier": (
                "CRITICAL (HF < 1.05)" if hf < 1.05
                else "HIGH (HF 1.05–1.2)" if hf < 1.2
                else "ELEVATED (HF 1.2–1.5)" if hf < 1.5
                else "SAFE"
            ),
        })

    if stats["excluded_unpriced_collateral"]:
        print(f"ℹ️ Excluded {stats['excluded_unpriced_collateral']} wallet(s) with unpriceable collateral (e.g. Pendle PT positions)")
    df = pd.DataFrame(rows)
    return (df.sort_values("health_factor").head(75) if not df.empty else df), stats


def fetch_high_risk_positions(top_reserves=5, borrowers_per_reserve=15):
    raw = fetch_raw_positions(top_reserves, borrowers_per_reserve)
    if raw.empty:
        return pd.DataFrame()
    all_symbols = set(raw["symbol"])
    tradeable = {s for s in all_symbols if not is_pendle_pt_token(s)}
    prices = fetch_live_prices(tradeable)
    missing = tradeable - set(prices.keys())
    pt_symbols = all_symbols - tradeable
    if missing:
        print(f"⚠️ No price found for (non-PT): {missing}")
    if pt_symbols:
        print(f"ℹ️ Excluded Pendle PT collateral (unsupported pricing): {pt_symbols}")
    df, stats = compute_positions(raw, prices)
    print("STATS:", stats)
    return df