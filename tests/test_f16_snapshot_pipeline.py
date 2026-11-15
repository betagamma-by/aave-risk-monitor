from unittest.mock import patch

import pandas as pd
import pytest

import data_fetcher as d


@patch(
    "historical_debt_verification.verify_negative_debt_at_block",
    return_value=0,
)
def test_prepare_balances_pins_gho(mock_verify):
    raw = pd.DataFrame({
        "symbol": ["WETH"],
        "atoken_now_raw": [1000],
        "debt_now_raw": [500],
    })

    with (
        patch(
            "data_fetcher.add_accrued_balances",
            return_value=raw,
        ) as accrue,
        patch(
            "data_fetcher.override_gho_debt",
            return_value=raw,
        ) as gho,
    ):
        d.prepare_balances(
            raw,
            now_ts=1700000000,
            block_identifier=12345,
        )

    accrue.assert_called_once_with(
        raw, now_ts=1700000000
    )
    gho.assert_called_once_with(
        raw, block_identifier=12345
    )


def test_historical_snapshot_requires_timestamp():
    with pytest.raises(ValueError, match="block_timestamp"):
        d.fetch_high_risk_positions(
            block_identifier=12345
        )


def test_prepare_requires_historical_timestamp():
    with pytest.raises(ValueError, match="now_ts"):
        d.prepare_balances(
            pd.DataFrame(),
            block_identifier=12345,
        )


def test_top_level_fetch_forwards_snapshot():
    raw = pd.DataFrame({
        "underlying": ["0xasset"],
        "symbol": ["WETH"],
    })
    result_df = pd.DataFrame({"wallet": ["0xabc"]})

    with (
        patch(
            "data_fetcher.fetch_raw_positions",
            return_value=raw,
        ) as fetch,
        patch(
            "data_fetcher.build_prices",
            return_value=({"0xasset": 2000}, "aave-oracle"),
        ) as prices,
        patch(
            "data_fetcher.prepare_balances",
            return_value=raw,
        ) as prepare,
        patch(
            "data_fetcher.compute_positions",
            return_value=(result_df, {}),
        ),
    ):
        result = d.fetch_high_risk_positions(
            top_reserves=5,
            borrowers_per_reserve=15,
            return_inputs=True,
            block_identifier=12345,
            block_timestamp=1700000000,
        )

    fetch.assert_called_once_with(
        5, 15, block_identifier=12345
    )
    prices.assert_called_once_with(
        raw, block_identifier=12345
    )
    prepare.assert_called_once_with(
        raw,
        now_ts=1700000000,
        block_identifier=12345,
    )
    assert result[1]["price_source"] == "aave-oracle"


def test_prepare_balances_stops_on_historical_verification_failure():
    with (
        patch(
            "historical_debt_verification.verify_negative_debt_at_block",
            side_effect=RuntimeError("On-chain debt mismatch"),
        ),
        patch("data_fetcher.add_accrued_balances") as accrue,
        patch("data_fetcher.override_gho_debt") as gho,
    ):
        with pytest.raises(RuntimeError, match="On-chain debt mismatch"):
            d.prepare_balances(
                pd.DataFrame({"symbol": ["WETH"]}),
                now_ts=1700000000,
                block_identifier=12345,
            )

        accrue.assert_not_called()
        gho.assert_not_called()
