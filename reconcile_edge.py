import os, random
import pandas as pd
from web3 import Web3
import data_fetcher as d

POOL_ABI = [{"name": "getUserAccountData", "type": "function", "stateMutability": "view",
             "inputs": [{"name": "user", "type": "address"}],
             "outputs": [{"name": n, "type": "uint256"} for n in
                         ["totalCollateralBase", "totalDebtBase", "availableBorrowsBase",
                          "currentLiquidationThreshold", "ltv", "healthFactor"]]}]
w3 = Web3(Web3.HTTPProvider(os.environ["ETH_RPC_URL"], request_kwargs={"timeout": 20}))
pool = w3.eth.contract(address=Web3.to_checksum_address(os.environ["AAVE_POOL_ADDRESS"]), abi=POOL_ABI)

def aave_hf(wallet):
    _, debt, _, _, _, hf = pool.functions.getUserAccountData(Web3.to_checksum_address(wallet)).call()
    return None if debt == 0 else hf / 1e18

def flag_wallets(raw, prices):
    """Label wallets that exercise edge cases."""
    acc = d.add_accrued_balances(raw)
    acc["price"] = acc["underlying"].map(prices).fillna(0)
    acc["coll_usd"] = (acc["atoken_now_raw"] / 10.0 ** acc["decimals"].astype(int)
                       * acc["price"] * acc["collateral_enabled"].astype(float))
    acc["listed"] = acc["emode_lt_bps"] > 0
    out = {}
    for w, g in acc.groupby("wallet"):
        c = g[g["coll_usd"] > 100]
        f = []
        if g["emode_id"].iloc[0] > 0 and c["listed"].any() and (~c["listed"]).any():
            f.append("mixed")                                   # listed AND unlisted collateral in eMode
        if (g["stable_debt_raw"].astype(float) > 0).any():
            f.append("stable_debt")
        if c["symbol"].str.startswith("PT-").any():
            f.append("pt_collateral")
        out[w] = f
    return out

random.seed(7)
raw = d.fetch_raw_positions(8, 60)                              # wider than before: up to ~480 wallets
main_wallets = set(raw["wallet"])
print("main population:", len(main_wallets), "wallets")
prices, _ = d.build_prices(raw)
flags = flag_wallets(raw, prices)

n_mixed = sum("mixed" in f for f in flags.values())
if n_mixed < 5:
    print(f"Only {n_mixed} mixed wallets in the main population; scanning eMode users directly...")
    try:
        ids = [u["id"] for u in d._gql(
            '{ users(first: 300, orderBy: id, where: { eModeCategoryId_not: null }) { id } }')["users"]]
        extra = d.fetch_raw_for_wallets(set(ids) - main_wallets)
        raw = pd.concat([raw, extra], ignore_index=True)
        prices, _ = d.build_prices(raw)
        flags = flag_wallets(raw, prices)
    except Exception as e:
        print("eMode scan failed:", str(e)[:200])

fresh, stats = d.compute_positions(raw, prices, accrue=True)
fresh = fresh.set_index("wallet_full")

pop_main = [w for w in fresh.index if w in main_wallets]
available = {"random_main": len(pop_main)}
groups = {"random_main": random.sample(pop_main, min(100, len(pop_main)))}
for name in ["mixed", "stable_debt", "pt_collateral"]:
    ws = [w for w in fresh.index if name in flags.get(w, [])]
    available[name] = len(ws)
    groups[name] = random.sample(ws, min(15, len(ws)))
small = [w for w in pop_main if fresh.loc[w, "debt_usd"] < 50_000]
available["small_debt"] = len(small)
groups["small_debt"] = random.sample(small, min(15, len(small)))
print("wallets available per group:", available)
print("wallets tested per group:   ", {k: len(v) for k, v in groups.items()})

cache = {}
for w in {w for ws in groups.values() for w in ws}:
    try:
        cache[w] = aave_hf(w)
    except Exception as e:
        print("call failed", w[:10], str(e)[:80])

rows = []
for g, ws in groups.items():
    for w in ws:
        a = cache.get(w)
        if a is None:
            continue
        ours = fresh.loc[w, "health_factor"]
        rows.append({"group": g, "wallet": w, "emode": int(fresh.loc[w, "emode_id"]),
                     "debt_usd": round(fresh.loc[w, "debt_usd"]), "aave_hf": round(a, 4),
                     "our_hf": ours, "err_%": round((ours / a - 1) * 100, 4)})
out = pd.DataFrame(rows)
out["abs_err"] = out["err_%"].abs()
print("\nabsolute error vs Aave (%), by group:")
print(out.groupby("group")["abs_err"].agg(n="count", median="median",
      p95=lambda s: s.quantile(.95), max="max").round(4).to_string())
print("\nlargest errors:")
print(out.nlargest(10, "abs_err")[["group", "wallet", "emode", "debt_usd", "aave_hf", "our_hf", "err_%"]].to_string(index=False))
print("\nstats:", stats)