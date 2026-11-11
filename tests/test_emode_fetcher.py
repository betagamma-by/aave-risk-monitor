
from decimal import Decimal

import pandas as pd
import pytest

from emode_fetcher import (
    used_emode_ids,
    applicable_liquidation_bonus,
)


def test_collect_all_used_categories():
    raw = pd.DataFrame({
        "emode_id": [0, 1, 2, 1, 5, 0]
    })

    assert used_emode_ids(raw) == [1, 2, 5]


def test_no_emode_categories():
    raw = pd.DataFrame({"emode_id": [0, 0]})

    assert used_emode_ids(raw) == []


def sample_configs():
    reserves = {
        "0xaaa": {
            "liquidation_bonus_pct": Decimal("0.05"),
            "collateral_liquidation_enabled": True,
            "is_active": True,
            "is_paused": False,
        }
    }

    categories = {
        1: {
            "liquidation_bonus_pct": Decimal("0.01"),
            "collateral_addresses": {"0xaaa"},
        },
        2: {
            "liquidation_bonus_pct": Decimal("0.02"),
            "collateral_addresses": {"0xbbb"},
        },
    }

    return reserves, categories


def test_eligible_emode_uses_category_bonus():
    reserves, categories = sample_configs()

    bonus = applicable_liquidation_bonus(
        1, "0xAAA", reserves, categories
    )

    assert bonus == Decimal("0.01")


def test_ineligible_asset_uses_base_bonus():
    reserves, categories = sample_configs()

    bonus = applicable_liquidation_bonus(
        2, "0xaaa", reserves, categories
    )

    assert bonus == Decimal("0.05")


def test_missing_category_rejected():
    reserves, categories = sample_configs()

    with pytest.raises(ValueError, match="Missing eMode"):
        applicable_liquidation_bonus(
            3, "0xaaa", reserves, categories
        )


def test_paused_collateral_rejected():
    reserves, categories = sample_configs()
    reserves["0xaaa"]["is_paused"] = True

    with pytest.raises(ValueError, match="inactive or paused"):
        applicable_liquidation_bonus(
            0, "0xaaa", reserves, categories
        )