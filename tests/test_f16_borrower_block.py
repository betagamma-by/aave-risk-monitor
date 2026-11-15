from unittest.mock import patch
import pandas as pd

from data_fetcher import (
    rank_reserves_by_usd,
    fetch_raw_for_wallets,
    fetch_raw_positions,
)


def test_reserve_ranking_forwards_block():
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
        patch("data_fetcher._gql", return_value=response) as gql,
        patch(
            "data_fetcher.build_prices",
            return_value=({"0xasset": 2000}, "aave-oracle"),
        ),
    ):
        result = rank_reserves_by_usd(1, block_identifier=12345)

    assert result[0]["id"] == "reserve1"
    assert gql.call_args.kwargs["block_identifier"] == 12345


def test_wallet_details_forward_block():
    with patch(
        "data_fetcher._gql",
        return_value={"users": [{"id": "0xabc", "reserves": []}]},
    ) as gql:
        fetch_raw_for_wallets(["0xabc"], block_identifier=12345)

    assert gql.call_args.kwargs["block_identifier"] == 12345


def test_borrower_discovery_forwards_block():
    with (
        patch(
            "data_fetcher.rank_reserves_by_usd",
            return_value=[{"id": "reserve1", "symbol": "WETH"}],
        ) as rank,
        patch(
            "data_fetcher._gql",
            return_value={
                "userReserves": [{"user": {"id": "0xabc"}}]
            },
        ) as gql,
        patch(
            "data_fetcher.fetch_raw_for_wallets",
            return_value=pd.DataFrame(),
        ) as wallets,
    ):
        fetch_raw_positions(
            top_reserves=1,
            borrowers_per_reserve=10,
            block_identifier=12345,
        )

    assert rank.call_args.kwargs["block_identifier"] == 12345
    assert gql.call_args.kwargs["block_identifier"] == 12345
    assert wallets.call_args.kwargs["block_identifier"] == 12345
