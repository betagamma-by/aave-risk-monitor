
"""Read Aave V3 reserve configurations from the configured Pool."""

import os

from web3 import Web3

from reserve_config import decode_reserve_configuration


POOL_ABI = [
    {
        "type": "function",
        "name": "getConfiguration",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [{
            "name": "",
            "type": "tuple",
            "components": [{"name": "data", "type": "uint256"}],
        }],
    },
    {
        "type": "function",
        "name": "getReservesList",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address[]"}],
    },
]


def fetch_reserve_configs(addresses=None):
    """Fetch actual Ethereum Aave V3 reserve configuration."""

    rpc_url = os.environ["ETH_RPC_URL"]
    pool_address = os.environ["AAVE_POOL_ADDRESS"]

    w3 = Web3(
        Web3.HTTPProvider(
            rpc_url,
            request_kwargs={"timeout": 20},
        )
    )

    if w3.eth.chain_id != 1:
        raise ValueError("Expected Ethereum mainnet (chain ID 1)")

    pool_address = Web3.to_checksum_address(pool_address)

    if not w3.eth.get_code(pool_address):
        raise ValueError("Configured Aave Pool has no contract code")

    pool = w3.eth.contract(
        address=pool_address,
        abi=POOL_ABI,
    )

    # Use one Ethereum block for the reserve list and configurations.
    block = w3.eth.block_number

    known_reserves = {
        addr.lower()
        for addr in pool.functions.getReservesList().call(
            block_identifier=block
        )
    }

    requested = (
        known_reserves
        if addresses is None
        else {a.lower() for a in addresses}
    )

    results = {}

    for address in sorted(requested):
        if address not in known_reserves:
            raise ValueError(f"Asset not listed in Pool: {address}")

        checksum = Web3.to_checksum_address(address)

        response = pool.functions.getConfiguration(
            checksum
        ).call(block_identifier=block)

        packed = int(response[0])
        config = decode_reserve_configuration(packed)

        results[address] = {
            **config,
            "block_number": block,
            "pool_address": pool_address,
            "chain_id": 1,
        }

    return results
