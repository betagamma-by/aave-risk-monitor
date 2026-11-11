
import pandas as pd

from reserve_validation import validate_reserve_metadata


def sample():
    raw = pd.DataFrame([{
        "underlying": "0xAAA",
        "symbol": "WETH",
        "decimals": 18,
        "base_lt_bps": 8400,
    }])

    configs = {
        "0xaaa": {
            "decimals": 18,
            "liquidation_threshold_bps": 8400,
        }
    }

    return raw, configs


def test_matching_reserve_metadata():
    raw, configs = sample()
    assert validate_reserve_metadata(raw, configs) == []


def test_decimals_mismatch():
    raw, configs = sample()
    raw.loc[0, "decimals"] = 6

    issues = validate_reserve_metadata(raw, configs)

    assert len(issues) == 1
    assert issues[0]["issue"] == "Token decimals mismatch"


def test_liquidation_threshold_mismatch():
    raw, configs = sample()
    raw.loc[0, "base_lt_bps"] = 8000

    issues = validate_reserve_metadata(raw, configs)

    assert issues[0]["issue"] == "Base liquidation threshold mismatch"


def test_missing_config():
    raw, _ = sample()

    issues = validate_reserve_metadata(raw, {})

    assert issues[0]["issue"] == "Missing on-chain configuration"
