from unittest.mock import patch

import pandas as pd

from data_fetcher import build_prices, rank_reserves_by_usd


def test_build_prices_forwards_snapshot_block():
    raw = pd.DataFrame([
        {"underlying": "0xasset", "symbol": "WETH"}
    ])

    with (
        patch.dict(
            "os.environ",
            {
                "ETH_RPC_URL": "http://mock-rpc",
                "AAVE_ORACLE_ADDRESS": "0xmock",
            },
        ),
        patch(
            "data_fetcher.fetch_aave_prices",
            return_value={"0xasset": 2000},
        ) as oracle,
    ):
        prices, source = build_prices(
            raw, block_identifier=12345
        )

    assert source == "aave-oracle"
    assert prices == {"0xasset": 2000}
    oracle.assert_called_once_with(
        {"0xasset"}, block_identifier=12345
    )


def test_reserve_ranking_forwards_block_to_prices():
    response = {
        "reserves": [{
            "id": "reserve1",
            "symbol": "WETH",
            "underlyingAsset": "0xasset",
            "decimals": 18,
            "totalCurrentVariableDebt": "1000000000000000000",
            "totalPrincipalStableDebt": "0",
        }]
    }

    with (
        patch(
            "data_fetcher._gql",
            return_value=response,
        ),
        patch(
            "data_fetcher.build_prices",
            return_value=(
                {"0xasset": 2000},
                "aave-oracle",
            ),
        ) as prices,
    ):
        result = rank_reserves_by_usd(
            1, block_identifier=12345
        )

    assert len(result) == 1
    assert prices.call_args.kwargs[
        "block_identifier"
    ] == 12345
