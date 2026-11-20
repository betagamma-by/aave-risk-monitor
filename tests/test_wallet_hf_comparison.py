from decimal import Decimal

import pytest

from wallet_hf_comparison import compare_wallet_health_factors
from current_wallet_verification import fetch_current_wallet_account


def test_model_and_chain_differences_are_separate():
    result = compare_wallet_health_factors(
        "1.25", "1.24", "1.80"
    )

    assert result["model_delta"] == Decimal("0.01")
    assert result["chain_delta"] == Decimal("0.56")
    assert result["model_error_pct"] > 0


def test_matching_historical_hf():
    result = compare_wallet_health_factors(
        "1.25", "1.25", "1.26"
    )
    assert result["model_delta"] == 0


def test_no_debt_is_not_treated_as_zero_hf():
    result = compare_wallet_health_factors(
        None, None, None
    )
    assert result["model_delta"] is None
    assert result["chain_delta"] is None


def test_invalid_hf_rejected():
    with pytest.raises(ValueError):
        compare_wallet_health_factors("-1", "1", "1")


def test_invalid_historical_block_rejected():
    with pytest.raises(ValueError, match="Invalid historical block"):
        fetch_current_wallet_account(
            "0x0000000000000000000000000000000000000001",
            block_identifier=-1
        )
