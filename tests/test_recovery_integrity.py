import pytest

from data_integrity_errors import DataIntegrityError
from recovery import load_with_fallback


def test_integrity_failure_does_not_call_snapshot():
    calls = []

    def live(*args):
        raise DataIntegrityError("Historical debt mismatch")

    def snapshot():
        calls.append("snapshot")
        raise AssertionError("Recovery must not run")

    with pytest.raises(DataIntegrityError, match="Historical debt mismatch"):
        load_with_fallback(live, snapshot, 8, 60)

    assert calls == []


def test_transient_failure_still_allows_recovery():
    def live(*args):
        raise ConnectionError("Subgraph unavailable")

    def snapshot():
        return (
            "recovered_positions",
            {"wallets_fetched": 1},
            "captured_at",
            {"price_source": "aave-oracle"},
        )

    result = load_with_fallback(live, snapshot, 8, 60)

    assert result[0] == "recovered_positions"
    assert result[4] == "snapshot"
    assert result[5] is None
