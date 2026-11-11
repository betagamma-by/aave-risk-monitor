
"""Fetch eMode configurations for categories used by monitored wallets."""

import os
from decimal import Decimal

from web3 import Web3

from emode_config import collateral_allowed


EMODE_ABI = [
    {
        "type": "function",
        "name": "getEModeCategoryCollateralConfig",
        "stateMutability": "view",
        "inputs": [{"name": "id", "type": "uint8"}],
        "outputs": [{
            "name": "",
            "type": "tuple",
            "components": [
                {"name": "ltv", "type": "uint16"},
                {"name": "liquidationThreshold", "type": "uint16"},
                {"name": "liquidationBonus", "type": "uint16"},
            ],
        }],
    },
    {
        "type": "function",
        "name": "getEModeCategoryCollateralBitmap",
        "stateMutability": "view",
        "inputs": [{"name": "id", "type": "uint8"}],
        "outputs": [{"name": "", "type": "uint128"}],
    },
    {
        "type": "function",
        "name": "getReserveAddressById",
        "stateMutability": "view",
        "inputs": [{"name": "id", "type": "uint16"}],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "getReservesList",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address[]"}],
    },
]


def used_emode_ids(prepared_raw):
    """Return all nonzero eMode IDs in the monitored population."""
    if "emode_id" not in prepared_raw.columns:
        raise ValueError("Missing emode_id column")

    ids = set()

    for value in prepared_raw["emode_id"]:
        if value is None:
            raise ValueError("Missing borrower eMode category")

        try:
            category = int(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Invalid borrower eMode category") from None

        if str(value) != str(category):
            raise ValueError("Invalid borrower eMode category")

        if not 0 <= category <= 255:
            raise ValueError("eMode category outside uint8 range")

        if category:
            ids.add(category)

    return sorted(ids)


def fetch_emode_configs(category_ids):
    """Fetch all requested eMode categories at one Ethereum block."""
    ids = sorted(set(category_ids))

    for category in ids:
        if (
            isinstance(category, bool)
            or not isinstance(category, int)
            or not 1 <= category <= 255
        ):
            raise ValueError("Invalid eMode category ID")

    if not ids:
        return {}

    w3 = Web3(Web3.HTTPProvider(
        os.environ["ETH_RPC_URL"],
        request_kwargs={"timeout": 20},
    ))

    if w3.eth.chain_id != 1:
        raise ValueError("Expected Ethereum mainnet")

    pool_address = Web3.to_checksum_address(
        os.environ["AAVE_POOL_ADDRESS"]
    )

    if not w3.eth.get_code(pool_address):
        raise ValueError("Pool contract not found")

    pool = w3.eth.contract(
        address=pool_address,
        abi=EMODE_ABI,
    )

    block = w3.eth.block_number

    known_reserves = {
        address.lower()
        for address in pool.functions.getReservesList().call(
            block_identifier=block
        )
    }

    result = {}
    address_cache = {}

    for category in ids:
        ltv, threshold, bonus = (
            pool.functions.getEModeCategoryCollateralConfig(
                category
            ).call(block_identifier=block)
        )

        bitmap = pool.functions.getEModeCategoryCollateralBitmap(
            category
        ).call(block_identifier=block)

        if not (0 < ltv <= threshold <= 10000):
            raise ValueError(
                f"Invalid eMode category configuration: {category}"
            )

        if bonus <= 10000:
            raise ValueError(
                f"Invalid eMode liquidation bonus: {category}"
            )

        eligible = set()

        for reserve_id in range(128):
            if not collateral_allowed(bitmap, reserve_id):
                continue

            if reserve_id not in address_cache:
                address_cache[reserve_id] = (
                    pool.functions.getReserveAddressById(
                        reserve_id
                    ).call(block_identifier=block).lower()
                )

            address = address_cache[reserve_id]

            if address not in known_reserves:
                raise ValueError(
                    f"Unlisted reserve ID {reserve_id} "
                    f"in eMode category {category}"
                )

            eligible.add(address)

        result[category] = {
            "ltv_bps": ltv,
            "liquidation_threshold_bps": threshold,
            "liquidation_bonus_bps": bonus,
            "liquidation_bonus_pct": (
                Decimal(bonus) - Decimal(10000)
            ) / Decimal(10000),
            "collateral_addresses": eligible,
            "block_number": block,
            "pool_address": pool_address,
        }

    return result


def applicable_liquidation_bonus(
    emode_id, collateral_address, reserve_configs, emode_configs
):
    """Return the base or eMode bonus for selected collateral."""
    address = collateral_address.lower()

    if address not in reserve_configs:
        raise ValueError("Missing base reserve configuration")

    base = reserve_configs[address]

    if not base.get("collateral_liquidation_enabled", False):
        raise ValueError("Selected reserve is not collateral-enabled")

    if not base.get("is_active", False) or base.get("is_paused", True):
        raise ValueError("Selected collateral reserve is inactive or paused")

    if emode_id == 0:
        return base["liquidation_bonus_pct"]

    if emode_id not in emode_configs:
        raise ValueError("Missing eMode configuration")

    category = emode_configs[emode_id]

    if address in category["collateral_addresses"]:
        return category["liquidation_bonus_pct"]

    return base["liquidation_bonus_pct"]
