import requests
import pandas as pd
import numpy as np
import time 
import os 
from decimal import Decimal, localcontext
SECONDS_PER_YEAR = 365 * 24 * 3600

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

ORACLE_ABI = [
    {"name": "getAssetsPrices", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "assets", "type": "address[]"}],
     "outputs": [{"name": "", "type": "uint256[]"}]},
    {"name": "getAssetPrice", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "asset", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "BASE_CURRENCY_UNIT", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint256"}]},
]


def fetch_aave_prices(addresses):
    """USD price per underlying address, straight from Aave's oracle. Keys are lowercase."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(os.environ["ETH_RPC_URL"], request_kwargs={"timeout": 20}))
    oracle = w3.eth.contract(address=Web3.to_checksum_address(os.environ["AAVE_ORACLE_ADDRESS"]),
                             abi=ORACLE_ABI)
    unit = oracle.functions.BASE_CURRENCY_UNIT().call()   # fails loudly if this isn't the oracle
    addrs = sorted(addresses)
    checksummed = [Web3.to_checksum_address(a) for a in addrs]
    try:
        raw_prices = oracle.functions.getAssetsPrices(checksummed).call()
        prices = dict(zip(addrs, raw_prices))
    except Exception:
        prices = {}                                         # batch failed: try one by one
        for a, c in zip(addrs, checksummed):
            try:
                prices[a] = oracle.functions.getAssetPrice(c).call()
            except Exception:
                prices[a] = 0
    return {a: p / unit for a, p in prices.items() if p > 0}

def build_prices(raw):
    """Aave oracle if the env vars are set, otherwise the old CoinGecko path."""
    addrs = set(raw["underlying"])
    if os.environ.get("ETH_RPC_URL") and os.environ.get("AAVE_ORACLE_ADDRESS"):
        return fetch_aave_prices(addrs), "aave-oracle"
    sym = raw.drop_duplicates("underlying").set_index("underlying")["symbol"].to_dict()
    cg = fetch_live_prices({s for s in sym.values() if not is_pendle_pt_token(s)})
    return {a: cg[s] for a, s in sym.items() if s in cg}, "coingecko"

def rank_reserves_by_usd(top_n):
    """Pick the reserves with the largest USD debt (variable + stable), not raw token units."""
    res = _gql("""{ reserves(first: 200) { id symbol decimals underlyingAsset
                   totalCurrentVariableDebt totalPrincipalStableDebt } }""")["reserves"]
    df = pd.DataFrame(res)
    if df.empty:
        raise ValueError("No reserves found")
    df["underlying"] = df["underlyingAsset"].str.lower()
    prices, source = build_prices(df[["underlying", "symbol"]])
    tokens = (df["totalCurrentVariableDebt"].astype(float)
              + df["totalPrincipalStableDebt"].astype(float)) / 10.0 ** df["decimals"].astype(int)
    df["debt_usd"] = tokens * df["underlying"].map(prices).fillna(0)

    unpriced = sorted(df.loc[(tokens > 1) & ~df["underlying"].isin(prices), "symbol"])
    if unpriced:
        print(f"⚠️ Reserves with debt but no price (not ranked): {unpriced}")
    ranked = df[df["debt_usd"] > 0].sort_values("debt_usd", ascending=False)
    print(f"Reserves ranked by USD debt ({source}); top 10:")
    print(ranked.head(10).assign(debt_usd_M=lambda x: (x["debt_usd"] / 1e6).round(1))
          [["symbol", "debt_usd_M"]].to_string(index=False))
    return ranked.head(top_n)[["id", "symbol"]].to_dict("records")

def fetch_raw_for_wallets(wallets):
    """Detailed positions for the given wallet ids: one row per wallet-reserve."""
    wallets = sorted(wallets)
    rows = []
    for i in range(0, len(wallets), 100):               # batches of 100 keep each query small
        wallets_filter = str(wallets[i:i + 100]).replace("'", '"')
        users = _gql(
            """{ users(first: 1000, where: { id_in: %s }) {
                id
                eModeCategoryId { id liquidationThreshold assets { asset collateral } }
                reserves { currentATokenBalance currentTotalDebt usageAsCollateralEnabledOnUser
                    scaledATokenBalance scaledVariableDebt currentStableDebt
                    reserve { symbol decimals reserveLiquidationThreshold underlyingAsset
                        liquidityIndex variableBorrowIndex liquidityRate variableBorrowRate
                        lastUpdateTimestamp } } } }"""
            % wallets_filter
        )["users"]
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
                    "atoken_balance_raw": r["currentATokenBalance"],
                    "debt_raw": r["currentTotalDebt"],
                    "collateral_enabled": bool(r["usageAsCollateralEnabledOnUser"]),
                    "emode_id": cat_id,
                    "emode_lt_bps": cat_lt if in_category else 0,
                    "scaled_atoken_raw": r["scaledATokenBalance"],
                    "scaled_vdebt_raw": r["scaledVariableDebt"],
                    "stable_debt_raw": r["currentStableDebt"],
                    "liq_index": res["liquidityIndex"],
                    "borrow_index": res["variableBorrowIndex"],
                    "liq_rate": res["liquidityRate"],
                    "borrow_rate": res["variableBorrowRate"],
                    "reserve_updated_ts": res["lastUpdateTimestamp"],
                })
    return pd.DataFrame(rows)


def fetch_raw_positions(top_reserves=5, borrowers_per_reserve=15):
    reserves = rank_reserves_by_usd(top_reserves)
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
    return fetch_raw_for_wallets(wallets)

def add_accrued_balances(raw, now_ts=None):
    """Grow balances to now: scaled balance x reserve index, with the index extended from the
    reserve's last update to now using its current rate (supply: linear, borrow: compounded)."""
    now_ts = now_ts or time.time()
    r = raw.copy()
    dt = (now_ts - r["reserve_updated_ts"].astype(float)).clip(lower=0)
    liq = r["liq_index"].astype(float) / 1e27 * (1 + r["liq_rate"].astype(float) / 1e27 * dt / SECONDS_PER_YEAR)
    bor = r["borrow_index"].astype(float) / 1e27 * np.exp(r["borrow_rate"].astype(float) / 1e27 * dt / SECONDS_PER_YEAR)
    r["atoken_now_raw"] = r["scaled_atoken_raw"].astype(float) * liq
    r["debt_now_raw"] = r["scaled_vdebt_raw"].astype(float) * bor + r["stable_debt_raw"].astype(float)
    return r

def override_gho_debt(raw):
    """Replace GHO debt with its actual on-chain debt-token balance."""
    from web3 import Web3

    gho_mask = raw["symbol"] == "GHO"
    if not gho_mask.any():
        return raw

    w3 = Web3(Web3.HTTPProvider(
        os.environ["ETH_RPC_URL"],
        request_kwargs={"timeout": 20}
    ))

    def abi_fn(name, inputs, outputs):
        return {
            "name": name,
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"type": t} for t in inputs],
            "outputs": [{"type": t} for t in outputs],
        }

    pool = w3.eth.contract(
        address=Web3.to_checksum_address(os.environ["AAVE_POOL_ADDRESS"]),
        abi=[abi_fn("ADDRESSES_PROVIDER", [], ["address"])]
    )

    provider_address = pool.functions.ADDRESSES_PROVIDER().call()
    provider = w3.eth.contract(
        address=provider_address,
        abi=[abi_fn("getPoolDataProvider", [], ["address"])]
    )

    data_provider_address = provider.functions.getPoolDataProvider().call()
    dp = w3.eth.contract(
        address=data_provider_address,
        abi=[abi_fn("getReserveTokensAddresses",
                    ["address"], ["address", "address", "address"])]
    )

    gho_address = Web3.to_checksum_address(
        raw.loc[gho_mask, "underlying"].iloc[0]
    )

    block = w3.eth.block_number

    _, _, debt_token_address = dp.functions.getReserveTokensAddresses(
        gho_address
    ).call(block_identifier=block)

    token = w3.eth.contract(
        address=debt_token_address,
        abi=[abi_fn("balanceOf", ["address"], ["uint256"])]
    )

    result = raw.copy()

    for wallet in result.loc[gho_mask, "wallet"].unique():
        debt = token.functions.balanceOf(
            Web3.to_checksum_address(wallet)
        ).call(block_identifier=block)

        result.loc[
            gho_mask & (result["wallet"] == wallet),
            "debt_now_raw"
        ] = float(debt)

    print(f"GHO override: {result.loc[gho_mask, 'wallet'].nunique()} "
          f"wallets, Ethereum block {block}")

    return result

def compute_positions(raw, prices, accrue=True):
    """prices: {lowercase underlying address: USD price}."""
    if not raw.empty:
        duplicates = raw.duplicated(
            subset=["wallet", "underlying"],
            keep=False
        )
        if duplicates.any():
            raise ValueError(
                "Duplicate wallet-reserve rows detected: "
                f"{int(duplicates.sum())} conflicting rows"
            )
    stats = {"wallets_fetched": 0, "wallets_in_emode": 0, "excluded_unpriced_collateral": 0,
             "excluded_unpriced_debt": 0, "dropped_debt_under_100": 0}
    if raw.empty:
        return pd.DataFrame(), stats
    stats["wallets_fetched"] = int(raw["wallet"].nunique())
    stats["wallets_in_emode"] = int((raw.groupby("wallet")["emode_id"].max() > 0).sum())

    if accrue:
        raw = add_accrued_balances(raw)
        raw = override_gho_debt(raw)
        a_col, d_col = "atoken_now_raw", "debt_now_raw"
    else:
        a_col, d_col = "atoken_balance_raw", "debt_raw"
    

    rows = []

    def dec(value):
        # Preserve exact integer and decimal-string inputs.
        # For float inputs, use their shortest decimal representation.
        return Decimal(str(value))

    with localcontext() as ctx:
        ctx.prec = 50

        for wallet, g in raw.groupby("wallet"):
            collateral_usd = Decimal(0)
            debt_usd = Decimal(0)
            weighted = Decimal(0)
            weighted_base = Decimal(0)
            max_val = Decimal(0)

            primary = None
            unpriced_collateral = False
            unpriced_debt = False

            for r in g.itertuples():
                scale = Decimal(10) ** int(r.decimals)

                balance_tokens = dec(getattr(r, a_col)) / scale
                debt_tokens = dec(getattr(r, d_col)) / scale

                price = dec(prices.get(r.underlying, 0))

                if price == 0:
                    if r.collateral_enabled and balance_tokens > Decimal("0.01"):
                        unpriced_collateral = True
                    if debt_tokens > Decimal("0.01"):
                        unpriced_debt = True
                    continue

                if r.collateral_enabled:
                    val = balance_tokens * price
                    collateral_usd += val

                    weighted_base += (
                        val * dec(r.base_lt_bps) / Decimal(10000)
                    )

                    weighted += (
                        val * dec(r.emode_lt_bps or r.base_lt_bps)
                        / Decimal(10000)
                    )

                    if val > max_val:
                        max_val = val
                        primary = r.symbol

                debt_usd += debt_tokens * price

            if unpriced_collateral:
                stats["excluded_unpriced_collateral"] += 1
                continue

            if unpriced_debt:
                stats["excluded_unpriced_debt"] += 1
                continue

            if debt_usd < Decimal(100):
                stats["dropped_debt_under_100"] += 1
                continue

            hf = weighted / debt_usd
            hf_base = weighted_base / debt_usd

            if hf < Decimal("1.05"):
                risk_tier = "CRITICAL (HF < 1.05)"
            elif hf < Decimal("1.2"):
                risk_tier = "HIGH (HF 1.05–1.2)"
            elif hf < Decimal("1.5"):
                risk_tier = "ELEVATED (HF 1.2–1.5)"
            else:
                risk_tier = "SAFE"

            rows.append({
                "wallet": wallet[:10] + "...",
                "wallet_full": wallet,
                "collateral_usd": round(float(collateral_usd), 2),
                "debt_usd": round(float(debt_usd), 2),
                "health_factor": float(hf),
                "health_factor_display": round(float(hf), 6),
                "health_factor_base": float(hf_base),
                "emode_id": int(g["emode_id"].iloc[0]),
                "primary_collateral": primary or "Unknown",
                "risk_tier": risk_tier,
            })

    df = pd.DataFrame(rows)
    return (df.sort_values("health_factor") if not df.empty else df), stats

def fetch_high_risk_positions(
    top_reserves=5,
    borrowers_per_reserve=15,
    return_stats=False
):
    raw = fetch_raw_positions(top_reserves, borrowers_per_reserve)

    if raw.empty:
        empty_stats = {
            "wallets_fetched": 0,
            "wallets_in_emode": 0,
            "excluded_unpriced_collateral": 0,
            "excluded_unpriced_debt": 0,
            "dropped_debt_under_100": 0,
            "price_source": "unknown",
        }
        return (pd.DataFrame(), empty_stats) if return_stats else pd.DataFrame()

    prices, source = build_prices(raw)
    unpriced = sorted(set(
        raw.loc[~raw["underlying"].isin(prices), "symbol"]
    ))
    if unpriced:
        print(f"Warning: No price for: {unpriced}")

    df, stats = compute_positions(raw, prices)
    stats["price_source"] = source
    print("STATS:", stats)

    return (df, stats) if return_stats else df
