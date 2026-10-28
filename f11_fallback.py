"""Read-only local Aave snapshot fallback. Never recompute old positions as live."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent / "snapshots"
REQUIRED = ("metadata.json", "computed_positions.parquet", "raw_positions.parquet", "prices.json")


def load_latest_snapshot():
    """Return (positions, stats, captured_at_utc, metadata) for latest valid snapshot."""
    if not ROOT.is_dir():
        raise FileNotFoundError("No local snapshots directory")

    candidates = sorted((p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")), reverse=True)
    for folder in candidates:
        try:
            if not all((folder / filename).is_file() for filename in REQUIRED):
                continue
            meta = json.loads((folder / "metadata.json").read_text())
            if meta.get("schema_version") != 1 or meta.get("price_source") != "aave-oracle":
                continue
            captured_at = datetime.fromisoformat(meta["completed_utc"].replace("Z", "+00:00"))
            if captured_at.tzinfo is None or captured_at > datetime.now(timezone.utc):
                continue
            df = pd.read_parquet(folder / "computed_positions.parquet")
            if df.empty or len(df) != int(meta["positions_saved"]):
                continue
            if "wallet_full" not in df or df["wallet_full"].duplicated().any():
                continue
            stats = meta.get("wallet_stats")
            if not isinstance(stats, dict):
                continue
            expected = (len(df) + int(stats["excluded_unpriced_collateral"])
                        + int(stats["excluded_unpriced_debt"])
                        + int(stats["dropped_debt_under_100"]))
            if expected != int(stats["wallets_fetched"]):
                continue
            return df, stats, captured_at, meta
        except (OSError, ValueError, KeyError, TypeError, ImportError):
            continue
    raise FileNotFoundError("No valid local snapshot available")
