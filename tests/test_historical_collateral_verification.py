import pandas as pd
import pytest

from data_integrity_errors import DataIntegrityError
from historical_collateral_verification import (
    normalize_verified_negative_collateral,
)


def sample(scaled="-3", balance="-2"):
    return pd.DataFrame([{
        "wallet": "0xwallet",
        "underlying": "0xasset",
        "symbol": "tBTC",
        "scaled_atoken_raw": scaled,
        "atoken_balance_raw": balance,
    }])


def test_verified_zero_normalized():
    calls = []

    def reader(wallet, asset):
        calls.append((wallet, asset))
        return (0, 0)

    result = normalize_verified_negative_collateral(
        sample(), 26426043, reader=reader
    )

    assert str(result.iloc[0]["scaled_atoken_raw"]) == "0"
    assert str(result.iloc[0]["atoken_balance_raw"]) == "0"
    assert len(calls) == 1


def test_positive_balances_unchanged():
    raw = sample("100", "101")
    result = normalize_verified_negative_collateral(raw, None)
    pd.testing.assert_frame_equal(raw, result)


def test_large_negative_rejected_without_rpc():
    with pytest.raises(DataIntegrityError, match="Untrusted"):
        normalize_verified_negative_collateral(
            sample("-3000000000000000000", "-3000000000000000000"),
            26426043,
            reader=lambda *_: pytest.fail("RPC must not be called"),
        )


def test_nonzero_onchain_rejected():
    with pytest.raises(DataIntegrityError, match="nonzero"):
        normalize_verified_negative_collateral(
            sample(),
            26426043,
            reader=lambda *_: (1, 1),
        )


def test_rpc_failure_rejected():
    def failing_reader(*_):
        raise TimeoutError("RPC unavailable")

    with pytest.raises(DataIntegrityError, match="FAILED"):
        normalize_verified_negative_collateral(
            sample(), 26426043, reader=failing_reader
        )


def test_unpinned_negative_rejected():
    with pytest.raises(DataIntegrityError, match="Historical block"):
        normalize_verified_negative_collateral(
            sample(), None, reader=lambda *_: (0, 0)
        )


def test_nonfinite_balance_rejected():
    with pytest.raises(DataIntegrityError, match="Non-finite"):
        normalize_verified_negative_collateral(
            sample("NaN", "-2"), 26426043
        )


def test_invalid_onchain_response_rejected():
    with pytest.raises(DataIntegrityError, match="Invalid on-chain"):
        normalize_verified_negative_collateral(
            sample(), 26426043, reader=lambda *_: (-1, 0)
        )
