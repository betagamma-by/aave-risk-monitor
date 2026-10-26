import os
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

raw = d.fetch_raw_positions(8, 25)
weth = raw[raw["symbol"] == "WETH"].iloc[0]
print("sanity: WETH supply APR %.4f | borrow APR %.4f (expect a few percent, i.e. 0.0x)"
      % (float(weth["liq_rate"]) / 1e27, float(weth["borrow_rate"]) / 1e27))
prices, _ = d.build_prices(raw)
stale, _ = d.compute_positions(raw, prices, accrue=False)
fresh, _ = d.compute_positions(raw, prices, accrue=True)
m = stale[["wallet_full", "health_factor"]].merge(
    fresh[["wallet_full", "health_factor", "emode_id"]], on="wallet_full", suffixes=("_stale", "_fresh"))

low = m.nsmallest(25, "health_factor_fresh")
sample = pd.concat([low, m.drop(low.index).sample(min(25, len(m) - 25), random_state=1)])

rows = []
for r in sample.itertuples():
    try:
        c, debt, _, lt, _, hf = pool.functions.getUserAccountData(Web3.to_checksum_address(r.wallet_full)).call()
    except Exception as e:
        print("call failed:", r.wallet_full, e)
        continue
    if debt == 0:
        continue
    rows.append({"wallet": r.wallet_full[:10], "emode": r.emode_id, "aave_hf": hf / 1e18,
                 "hf_stale": r.health_factor_stale, "hf_fresh": r.health_factor_fresh})
out = pd.DataFrame(rows)
out["err_stale_%"] = (out["hf_stale"] / out["aave_hf"] - 1) * 100
out["err_fresh_%"] = (out["hf_fresh"] / out["aave_hf"] - 1) * 100
print(out.round(4).to_string(index=False))
for c in ["err_stale_%", "err_fresh_%"]:
    e = out[c].abs()
    print(f"{c}: median {e.median():.3f}% | p95 {e.quantile(.95):.3f}% | max {e.max():.3f}% | n={len(e)}")