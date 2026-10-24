import pandas as pd
import old_data_fetcher as old
import data_fetcher as new

o = old.fetch_high_risk_positions()
n = new.fetch_high_risk_positions()
print("\nold rows:", len(o), "| new rows:", len(n))

m = o.merge(n, on="wallet_full", suffixes=("_old", "_new"))
print("wallets in both:", len(m))

# Test 1: new code's base-threshold HF must match old code's HF
d = (m["health_factor_base"] - m["health_factor_old"]).abs()
print("TEST 1 (refactor): max diff", round(d.max(), 4), "| median", round(d.median(), 4),
      "| wallets with diff > 0.01:", int((d > 0.01).sum()))

# Test 2: what eMode changed
e = n[n["emode_id"] > 0][["wallet_full", "emode_id", "health_factor_base", "health_factor"]]
print("\nTEST 2 (eMode): wallets in eMode:", len(e))
print(e.sort_values("health_factor").to_string(index=False))
w1 = n[n["wallet_full"] == "0x08c14b32c8a48894e4b933090ebcc9ce33b21135"]
print("\nwallet 1 (Aave on-chain said 1.0103 earlier):")
print(w1[["health_factor_base", "health_factor", "emode_id"]].to_string(index=False))