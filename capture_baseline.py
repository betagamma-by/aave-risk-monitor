import io, re, json, pathlib, subprocess, contextlib, datetime as dt
import requests
from data_fetcher import fetch_high_risk_positions, SUBGRAPH_URL

ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out = pathlib.Path("baselines/phase1"); out.mkdir(parents=True, exist_ok=True)

q = "{ reserves(first: 5, orderBy: totalCurrentVariableDebt, orderDirection: desc) { symbol decimals totalCurrentVariableDebt } }"
reserves = requests.post(SUBGRAPH_URL, json={"query": q}, timeout=30).json()["data"]["reserves"]

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    df = fetch_high_risk_positions(top_reserves=5, borrowers_per_reserve=15)
log = buf.getvalue()
m = re.search(r"Excluded (\d+) wallet", log)

df.to_csv(out / f"wallets_{ts}.csv", index=False)
(out / f"stdout_{ts}.txt").write_text(log)
summary = {
    "captured_utc": ts,
    "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
    "top5_reserves_as_selected": reserves,
    "wallets_in_final_table": int(len(df)),
    "wallets_excluded_unpriced_collateral": int(m.group(1)) if m else 0,
    "tier_counts": df["risk_tier"].value_counts().to_dict(),
    "total_debt_usd": float(df["debt_usd"].sum()),
    "hf_describe": df["health_factor"].describe(percentiles=[.05, .25, .5, .75, .95]).to_dict(),
}
(out / f"summary_{ts}.json").write_text(json.dumps(summary, indent=2))