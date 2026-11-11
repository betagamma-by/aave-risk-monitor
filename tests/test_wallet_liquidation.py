from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from wallet_liquidation import estimate_wallet_liquidation


def test_wallet_pair_uses_stressed_values():
    prepared = pd.DataFrame([
        {"wallet": "0xabc", "emode_id": 0},
    ])

    valued = pd.DataFrame([
        {
            "underlying": "0xdebt",
            "symbol": "USDC",
            "debt_usd": Decimal("10000"),
            "collateral_usd": Decimal("0"),
        },
        {
            "underlying": "0xcollateral",
            "symbol": "WETH",
            "debt_usd": Decimal("0"),
            "collateral_usd": Decimal("12000"),
        },
    ])

    stressed_prices = {
        "0xdebt": Decimal("1"),
        "0xcollateral": Decimal("2000"),
    }

    with (
        patch(
            "wallet_liquidation.value_wallet_reserves",
            return_value=valued,
        ) as value_mock,
        patch(
            "wallet_liquidation.applicable_liquidation_bonus",
            return_value=Decimal("0.05"),
        ) as bonus_mock,
        patch(
            "wallet_liquidation.estimate_liquidation_pair",
            return_value={
                "test_result": True,
                "repayable_debt_usd": Decimal("5000"),
                "collateral_seized_usd": Decimal("5250"),
                "remaining_debt_asset_usd": Decimal("5000"),
                "remaining_collateral_asset_usd": Decimal("6000"),
            },
        ) as pair_mock,
    ):
        result = estimate_wallet_liquidation(
            prepared_raw=prepared,
            stressed_prices=stressed_prices,
            wallet="0xabc",
            stressed_hf=Decimal("0.92"),
            debt_address="0xdebt",
            collateral_address="0xcollateral",
            reserve_configs={
                "0xcollateral": {
                    "liquidation_protocol_fee_bps": 2000,
                }
            },
            emode_configs={},
        )

    value_mock.assert_called_once_with(
        prepared, stressed_prices, "0xabc"
    )
    assert bonus_mock.call_args.args[0:2] == (0, "0xcollateral")

    args = pair_mock.call_args.kwargs
    assert args["selected_debt_usd"] == Decimal("10000")
    assert args["selected_collateral_usd"] == Decimal("12000")
    assert args["liquidation_bonus_pct"] == Decimal("0.05")
    assert args["total_debt_usd"] == Decimal("10000")
    assert args["total_collateral_usd"] == Decimal("12000")
    assert result["test_result"] is True
    assert result["protocol_fee_bps"] == 2000
    assert result["protocol_fee_usd"] == Decimal("50")
    assert result["liquidator_collateral_usd"] == Decimal("5200")
    assert result["net_bonus_before_costs_usd"] == Decimal("200")
    assert result["passes_dust_check"] is True
    assert result["clears_selected_debt"] is False
    assert result["clears_selected_collateral"] is False

@pytest.mark.parametrize("hf", ["1", "1.01", "0", "-0.1"])
def test_rejects_nonliquidatable_hf(hf):
    with pytest.raises(ValueError):
        estimate_wallet_liquidation(
            prepared_raw=pd.DataFrame(),
            stressed_prices={},
            wallet="0xabc",
            stressed_hf=hf,
            debt_address="0xdebt",
            collateral_address="0xcollateral",
            reserve_configs={},
            emode_configs={},
        )


def test_protocol_fee_comes_from_collateral_reserve():
    from unittest.mock import patch
    from wallet_liquidation import estimate_wallet_liquidation

    prepared = pd.DataFrame([
        {"wallet": "0xabc", "emode_id": 0},
    ])

    valued = pd.DataFrame([
        {
            "underlying": "0xdebt",
            "symbol": "USDC",
            "debt_usd": Decimal("10000"),
            "collateral_usd": Decimal("0"),
        },
        {
            "underlying": "0xcollateral",
            "symbol": "WETH",
            "debt_usd": Decimal("0"),
            "collateral_usd": Decimal("12000"),
        },
    ])

    configs = {
        "0xdebt": {"liquidation_protocol_fee_bps": 500},
        "0xcollateral": {"liquidation_protocol_fee_bps": 2000},
    }

    with (
        patch("wallet_liquidation.value_wallet_reserves", return_value=valued),
        patch(
            "wallet_liquidation.applicable_liquidation_bonus",
            return_value=Decimal("0.05"),
        ),
        patch(
            "wallet_liquidation.estimate_liquidation_pair",
            return_value={
                "repayable_debt_usd": Decimal("5000"),
                "collateral_seized_usd": Decimal("5250"),
                "remaining_debt_asset_usd": Decimal("5000"),
                "remaining_collateral_asset_usd": Decimal("6750"),
            },
        ),
    ):
        result = estimate_wallet_liquidation(
            prepared_raw=prepared,
            stressed_prices={},
            wallet="0xabc",
            stressed_hf=Decimal("0.92"),
            debt_address="0xdebt",
            collateral_address="0xcollateral",
            reserve_configs=configs,
            emode_configs={},
        )

    assert result["protocol_fee_bps"] == 2000
    assert result["protocol_fee_usd"] == Decimal("50")
    assert result["liquidator_collateral_usd"] == Decimal("5200")
