import pandas as pd
import pytest

from balance_normalization import normalize_negative_debt_dust


def sample(scaled, total, stable=0):
    return pd.DataFrame([{
        "wallet": "0xabc",
        "symbol": "LUSD",
        "scaled_vdebt_raw": str(scaled),
        "stable_debt_raw": str(stable),
        "debt_raw": str(total),
    }])


@pytest.mark.parametrize("scaled,total", [
    (-1, -1.25),
    (-2, -2.5),
    (-5, -6.3),
])
def test_tiny_negative_dust_normalized(scaled, total):
    result = normalize_negative_debt_dust(sample(scaled, total))
    assert result.iloc[0]["scaled_vdebt_raw"] == "0"
    assert result.iloc[0]["debt_raw"] == "0"


def test_valid_debt_unchanged():
    raw = sample(1000000, 1250000)
    result = normalize_negative_debt_dust(raw)
    assert result.iloc[0]["scaled_vdebt_raw"] == "1000000"


def test_large_negative_debt_rejected():
    with pytest.raises(ValueError, match="Untrusted"):
        normalize_negative_debt_dust(sample(-1000, -1250))


def test_negative_debt_with_stable_debt_rejected():
    with pytest.raises(ValueError, match="Untrusted"):
        normalize_negative_debt_dust(sample(-1, -1, stable=100))


def test_negative_total_with_nonnegative_scaled_rejected():
    with pytest.raises(ValueError, match="Unexpected"):
        normalize_negative_debt_dust(sample(0, -100))
