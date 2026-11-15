import os
from unittest.mock import patch

import pandas as pd
import pytest

from data_fetcher import build_prices


RAW = pd.DataFrame([
    {"underlying": "0xasset", "symbol": "WETH"}
])


def test_missing_oracle_configuration_rejected():
    with patch.dict(os.environ, {}, clear=True):
        with patch(
            "data_fetcher.fetch_live_prices",
            side_effect=AssertionError("CoinGecko must not be called"),
        ):
            with pytest.raises(
                RuntimeError, match="Aave Oracle configuration missing"
            ):
                build_prices(RAW)


def test_uses_aave_oracle_exclusively():
    with patch.dict(os.environ, {
        "ETH_RPC_URL": "http://mock-rpc",
        "AAVE_ORACLE_ADDRESS": "0xmock",
    }):
        with patch(
            "data_fetcher.fetch_aave_prices",
            return_value={"0xasset": 2000},
        ) as oracle:
            with patch(
                "data_fetcher.fetch_live_prices",
                side_effect=AssertionError("CoinGecko must not be called"),
            ):
                prices, source = build_prices(RAW)

    assert prices == {"0xasset": 2000}
    assert source == "aave-oracle"
    oracle.assert_called_once_with({"0xasset"})


def test_oracle_failure_does_not_fallback():
    with patch.dict(os.environ, {
        "ETH_RPC_URL": "http://mock-rpc",
        "AAVE_ORACLE_ADDRESS": "0xmock",
    }):
        with patch(
            "data_fetcher.fetch_aave_prices",
            side_effect=RuntimeError("RPC unavailable"),
        ):
            with patch(
                "data_fetcher.fetch_live_prices",
                side_effect=AssertionError("CoinGecko must not be called"),
            ):
                with pytest.raises(
                    RuntimeError, match="RPC unavailable"
                ):
                    build_prices(RAW)
