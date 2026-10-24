import pandas as pd
import data_fetcher as d

raw = d.fetch_raw_positions()
sym = raw.drop_duplicates("underlying").set_index("underlying")["symbol"].to_dict()
aave = d.fetch_aave_prices(set(raw["underlying"]))
cg_sym = d.fetch_live_prices({s for s in sym.values() if not d.is_pendle_pt_token(s)})
cg = {a: cg_sym[s] for a, s in sym.items() if s in cg_sym}

t = pd.DataFrame([{"symbol": s, "aave": aave.get(a), "coingecko": cg.get(a)} for a, s in sym.items()])
t["cg_vs_aave_%"] = (t["coingecko"] / t["aave"] - 1) * 100
print(t.sort_values("symbol").round(4).to_string(index=False))

dfa, sa = d.compute_positions(raw, aave)
dfc, sc = d.compute_positions(raw, cg)
print("\nAAVE stats:", sa)
print("CG stats:  ", sc)
m = dfc.merge(dfa, on="wallet_full", suffixes=("_cg", "_aave"))
diff = (m["health_factor_cg"] - m["health_factor_aave"]).abs()
print("\nwallets in both:", len(m), "| median |HF diff|:", round(diff.median(), 4),
      "| max:", round(diff.max(), 4))
print(m.loc[diff.nlargest(5).index, ["wallet_full", "health_factor_cg", "health_factor_aave"]].to_string(index=False))
print(dfa.nsmallest(5, "health_factor")[["wallet_full", "health_factor", "emode_id"]].to_string(index=False))