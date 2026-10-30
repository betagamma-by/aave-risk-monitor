
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from f11_fallback import load_latest_snapshot


WALLET = "0x1111111111111111111111111111111111111111"


def create_snapshot(root, name, *, valid=True, wallet_count=1):
    """Create a test snapshot without external services."""
    folder = root / name
    folder.mkdir(parents=True)

    captured = datetime.now(timezone.utc) - timedelta(hours=1)

    positions = pd.DataFrame([
        {
            "wallet_full": WALLET,
            "health_factor": 1.10,
            "debt_usd": 1000.0,
        }
    ])

    positions.to_parquet(folder / "computed_positions.parquet")
    positions.to_parquet(folder / "raw_positions.parquet")

    (folder / "prices.json").write_text(
        json.dumps({"test": 1.0})
    )

    metadata = {
        "schema_version": 1,
        "price_source": "aave-oracle",
        "completed_utc": captured.isoformat(),
        "positions_saved": wallet_count,
        "wallet_stats": {
            "wallets_fetched": 1,
            "excluded_unpriced_collateral": 0,
            "excluded_unpriced_debt": 0,
            "dropped_debt_under_100": 0,
        },
    }

    (folder / "metadata.json").write_text(json.dumps(metadata))

    if not valid:
        (folder / "prices.json").unlink()

    return folder


def test_valid_snapshot_loads(tmp_path):
    create_snapshot(tmp_path, "20261028T120000000000Z")

    positions, stats, captured, metadata = load_latest_snapshot(
        root=tmp_path
    )

    assert len(positions) == 1
    assert positions.iloc[0]["wallet_full"] == WALLET
    assert stats["wallets_fetched"] == 1
    assert metadata["price_source"] == "aave-oracle"


def test_incomplete_snapshot_is_rejected(tmp_path):
    create_snapshot(tmp_path, "20261028T120000000000Z", valid=False)

    with pytest.raises(FileNotFoundError):
        load_latest_snapshot(root=tmp_path)


def test_falls_back_to_older_valid_snapshot(tmp_path):
    create_snapshot(tmp_path, "20261028T120000000000Z")
    create_snapshot(tmp_path, "20261029T120000000000Z", valid=False)

    positions, stats, captured, metadata = load_latest_snapshot(
        root=tmp_path
    )

    assert len(positions) == 1
    assert stats["wallets_fetched"] == 1


def test_inconsistent_wallet_count_is_rejected(tmp_path):
    create_snapshot(
        tmp_path,
        "20261028T120000000000Z",
        wallet_count=999,
    )

    with pytest.raises(FileNotFoundError):
        load_latest_snapshot(root=tmp_path)
