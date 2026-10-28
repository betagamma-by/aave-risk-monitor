"""F11-A: capture one local, reproducible Aave monitor snapshot (no fallback yet)."""
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import data_fetcher as d

TOP_RESERVES = 8
BORROWERS_PER_RESERVE = 60
ROOT = Path(__file__).resolve().parent / "snapshots"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    from web3 import Web3

    if not os.getenv("ETH_RPC_URL") or not os.getenv("AAVE_ORACLE_ADDRESS"):
        raise RuntimeError("F11 snapshots require ETH_RPC_URL and AAVE_ORACLE_ADDRESS (no CoinGecko fallback).")

    # Record source metadata before fetching. These are observations, not a
    # guarantee that every input was read at the same block.
    graph_start = d._gql("{ _meta { block { number } hasIndexingErrors } }")["_meta"]
    if graph_start["hasIndexingErrors"]:
        raise RuntimeError("Subgraph reports indexing errors; snapshot aborted")

    w3 = Web3(Web3.HTTPProvider(os.environ["ETH_RPC_URL"], request_kwargs={"timeout": 20}))
    chain_start = w3.eth.block_number
    started_at = utc_now()

    raw = d.fetch_raw_positions(TOP_RESERVES, BORROWERS_PER_RESERVE)
    if raw.empty:
        raise RuntimeError("No positions returned; refusing to save empty snapshot")
    prices, price_source = d.build_prices(raw)
    if price_source != "aave-oracle":
        raise RuntimeError(f"Unexpected pricing source: {price_source}")
    positions, stats = d.compute_positions(raw, prices, accrue=True)
    if positions.empty:
        raise RuntimeError("No analyzed positions; refusing to save empty snapshot")
    if stats["wallets_fetched"] != (len(positions)
            + stats["excluded_unpriced_collateral"]
            + stats["excluded_unpriced_debt"]
            + stats["dropped_debt_under_100"]):
        raise RuntimeError("Wallet accounting mismatch; snapshot aborted")

    graph_end = d._gql("{ _meta { block { number } hasIndexingErrors } }")["_meta"]
    if graph_end["hasIndexingErrors"]:
        raise RuntimeError("Subgraph reports indexing errors after fetch; snapshot aborted")
    chain_end = w3.eth.block_number
    finished_at = utc_now()

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    metadata = {
        "schema_version": 1,
        "methodology": "phase2-fixes-gho-onchain-override",
        "git_commit": commit,
        "started_utc": started_at,
        "completed_utc": finished_at,
        "top_reserves": TOP_RESERVES,
        "borrowers_per_reserve": BORROWERS_PER_RESERVE,
        "price_source": price_source,
        "graph_block_before": int(graph_start["block"]["number"]),
        "graph_block_after": int(graph_end["block"]["number"]),
        "ethereum_head_before": int(chain_start),
        "ethereum_head_after": int(chain_end),
        "wallet_stats": stats,
        "positions_saved": len(positions),
        "note": "Source reads are not all pinned to one block. Historical research requires this caveat.",
    }

    ROOT.mkdir(exist_ok=True)
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = ROOT / tag
    temp = ROOT / (".incomplete-" + tag)
    temp.mkdir()
    try:
        raw.to_parquet(temp / "raw_positions.parquet", index=False)
        positions.to_parquet(temp / "computed_positions.parquet", index=False)
        (temp / "prices.json").write_text(json.dumps({k: float(v) for k, v in prices.items()}, indent=2))
        (temp / "metadata.json").write_text(json.dumps(metadata, indent=2))
        temp.rename(target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    print(f"Snapshot saved: {target}")
    print(f"Wallets: {len(positions)} / {stats['wallets_fetched']} fetched")
    print(f"Graph blocks: {metadata['graph_block_before']} -> {metadata['graph_block_after']}")
    print("Files: raw_positions.parquet, computed_positions.parquet, prices.json, metadata.json")


if __name__ == "__main__":
    main()