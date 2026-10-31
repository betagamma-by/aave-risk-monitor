
from datetime import datetime, timezone

import pandas as pd
import pytest

from recovery import load_with_fallback


def test_live_success_does_not_use_snapshot():
    now = datetime.now(timezone.utc)
    positions = pd.DataFrame({"wallet_full": ["0xabc"]})

    def load_live(*args):
        return positions, {"wallets_fetched": 1}, now, {"lag_blocks": 0}

    def load_snapshot():
        raise AssertionError("Snapshot should not be used")

    result = load_with_fallback(load_live, load_snapshot, 8, 60)

    assert result[4] == "live"
    assert len(result[0]) == 1


def test_live_failure_uses_snapshot():
    now = datetime.now(timezone.utc)
    positions = pd.DataFrame({"wallet_full": ["0xabc"]})

    def load_live(*args):
        raise ConnectionError("Live source unavailable")

    def load_snapshot():
        return (
            positions,
            {"wallets_fetched": 1},
            now,
            {"price_source": "aave-oracle", "graph_block": 123},
        )

    result = load_with_fallback(load_live, load_snapshot, 8, 60)

    assert result[4] == "snapshot"
    assert result[2] == now
    assert result[1]["price_source"] == "aave-oracle"
    assert result[3]["graph_block"] == 123


def test_both_sources_fail():
    def load_live(*args):
        raise ConnectionError("Live failed")

    def load_snapshot():
        raise FileNotFoundError("Snapshot missing")

    with pytest.raises(RuntimeError, match="Both live Aave data"):
        load_with_fallback(load_live, load_snapshot, 8, 60)
