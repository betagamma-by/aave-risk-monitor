"""Read-only current Aave V3 wallet-account verification."""

import os
from decimal import Decimal

from web3 import Web3


ACCOUNT_DATA_ABI = [{
    "type": "function",
    "name": "getUserAccountData",
    "stateMutability": "view",
    "inputs": [{"name": "user", "type": "address"}],
    "outputs": [
        {"name": "totalCollateralBase", "type": "uint256"},
        {"name": "totalDebtBase", "type": "uint256"},
        {"name": "availableBorrowsBase", "type": "uint256"},
        {"name": "currentLiquidationThreshold", "type": "uint256"},
        {"name": "ltv", "type": "uint256"},
        {"name": "healthFactor", "type": "uint256"},
    ],
}]


def fetch_current_wallet_account(wallet, rpc_url=None, pool_address=None, block_identifier=None):
    rpc = rpc_url or os.environ["ETH_RPC_URL"]
    pool_addr = pool_address or os.environ["AAVE_POOL_ADDRESS"]

    w3 = Web3(Web3.HTTPProvider(
        rpc,
        request_kwargs={"timeout": 20},
    ))

    if w3.eth.chain_id != 1:
        raise RuntimeError("Expected Ethereum mainnet")

    user = Web3.to_checksum_address(wallet)

    pool = w3.eth.contract(
        address=Web3.to_checksum_address(pool_addr),
        abi=ACCOUNT_DATA_ABI,
    )

    # Anchor the call to a specific current block.
    if block_identifier is not None and (
        isinstance(block_identifier, bool)
        or not isinstance(block_identifier, int)
        or block_identifier < 0
    ):
        raise ValueError("Invalid historical block identifier")

    block = (
        w3.eth.block_number
        if block_identifier is None
        else block_identifier
    )

    values = pool.functions.getUserAccountData(user).call(
        block_identifier=block
    )

    (
        collateral_base,
        debt_base,
        available_base,
        liquidation_threshold,
        ltv,
        health_factor,
    ) = values

    # Query the Aave Oracle at the SAME block as getUserAccountData.
    from data_fetcher import ORACLE_ABI

    oracle_address = Web3.to_checksum_address(
        os.environ["AAVE_ORACLE_ADDRESS"]
    )
    oracle = w3.eth.contract(
        address=oracle_address,
        abi=ORACLE_ABI,
    )

    unit = oracle.functions.BASE_CURRENCY_UNIT().call(
        block_identifier=block
    )

    if isinstance(unit, bool) or not isinstance(unit, int) or unit != 10**8:
        raise RuntimeError(
            f"Unexpected Aave Ethereum USD Oracle base unit: {unit}"
        )

    base_unit = Decimal(unit)
    wad = Decimal(10) ** 18

    return {
        "wallet": user.lower(),
        "block_number": block,
        "collateral_usd": Decimal(collateral_base) / base_unit,
        "debt_usd": Decimal(debt_base) / base_unit,
        "available_borrow_usd": Decimal(available_base) / base_unit,
        "liquidation_threshold_pct": Decimal(liquidation_threshold) / 100,
        "ltv_pct": Decimal(ltv) / 100,
        "health_factor": (
            Decimal(health_factor) / wad
            if debt_base > 0
            else None
        ),
        "has_debt": debt_base > 0,
    }
