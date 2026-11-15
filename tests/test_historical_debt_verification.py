import pandas as pd
import pytest

from historical_debt_verification import verify_negative_debt_at_block


def sample(scaled=-1, total=-1.25):
    return pd.DataFrame([{
        "wallet": "0xabc",
        "underlying": "0xasset",
        "symbol": "LUSD",
        "scaled_vdebt_raw": str(scaled),
        "stable_debt_raw": "0",
        "debt_raw": str(total),
    }])


def test_verified_zero_debt():
    calls = []

    def reader(wallet, asset):
        calls.append((wallet, asset))
        return (0, 0, 0)

    count = verify_negative_debt_at_block(
        sample(), 12345, reader=reader
    )
    assert count == 1
    assert calls == [("0xabc", "0xasset")]


def test_nonzero_onchain_debt_rejected():
    with pytest.raises(RuntimeError, match="FAILED"):
        verify_negative_debt_at_block(
            sample(), 12345,
            reader=lambda wallet, asset: (1, 1, 0),
        )


def test_rpc_failure_rejected():
    def reader(wallet, asset):
        raise ConnectionError("Historical RPC unavailable")

    with pytest.raises(RuntimeError, match="FAILED"):
        verify_negative_debt_at_block(
            sample(), 12345, reader=reader
        )


def test_large_negative_debt_rejected():
    with pytest.raises(RuntimeError, match="Untrusted"):
        verify_negative_debt_at_block(
            sample(-1000, -1250),
            12345,
            reader=lambda wallet, asset: (0, 0, 0),
        )


def test_clean_position_requires_no_rpc():
    def unexpected_rpc(wallet, asset):
        raise AssertionError("RPC should not be called")

    assert verify_negative_debt_at_block(
        sample(100, 125),
        12345,
        reader=unexpected_rpc,
    ) == 0


def test_invalid_block_rejected():
    with pytest.raises(ValueError, match="snapshot block"):
        verify_negative_debt_at_block(
            sample(), None,
            reader=lambda wallet, asset: (0, 0, 0),
        )
