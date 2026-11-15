"""Read-only historical RPC audit of normalized subgraph debt."""

import argparse
import os
from decimal import Decimal

from web3 import Web3

from balance_normalization import normalize_negative_debt_dust

POOL_ABI = [{
    "type": "function",
    "name": "ADDRESSES_PROVIDER",
    "stateMutability": "view",
    "inputs": [],
    "outputs": [{"type": "address"}],
}]

PROVIDER_ABI = [{
    "type": "function",
    "name": "getPoolDataProvider",
    "stateMutability": "view",
    "inputs": [],
    "outputs": [{"type": "address"}],
}]

DATA_ABI = [{
    "type": "function",
    "name": "getReserveTokensAddresses",
    "stateMutability": "view",
    "inputs": [{"name": "asset", "type": "address"}],
    "outputs": [
        {"type": "address"},
        {"type": "address"},
        {"type": "address"},
    ],
}]

DEBT_ABI = [
    {
        "type": "function",
        "name": name,
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    }
    for name in ("balanceOf", "scaledBalanceOf")
]


def is_verified_zero(variable_balance, scaled_balance, stable_balance):
    return (
        variable_balance == 0
        and scaled_balance == 0
        and stable_balance == 0
    )


def audit(block, top_reserves, borrowers_per_reserve):
    from data_fetcher import fetch_raw_positions

    w3 = Web3(Web3.HTTPProvider(
        os.environ["ETH_RPC_URL"],
        request_kwargs={"timeout": 30},
    ))

    if w3.eth.chain_id != 1:
        raise RuntimeError("Expected Ethereum mainnet RPC")

    snapshot = w3.eth.get_block(block)
    print(f"Historical snapshot: {snapshot['number']}")

    raw = fetch_raw_positions(
        top_reserves=top_reserves,
        borrowers_per_reserve=borrowers_per_reserve,
        block_identifier=block,
    )

    if raw.empty:
        raise RuntimeError("No borrower positions returned")

    # Reuse the exact normalizer used by the dashboard.
    normalize_negative_debt_dust(raw)

    affected = raw.loc[
        raw["scaled_vdebt_raw"].map(
            lambda x: Decimal(str(x)) < 0
        )
    ].copy()

    print(f"Positions retrieved: {len(raw)}")
    print(f"Dust corrections to audit: {len(affected)}")

    if affected.empty:
        raise RuntimeError(
            "No corrected positions found; audit is inconclusive"
        )

    pool = w3.eth.contract(
        address=Web3.to_checksum_address(
            os.environ["AAVE_POOL_ADDRESS"]
        ),
        abi=POOL_ABI,
    )

    provider_address = pool.functions.ADDRESSES_PROVIDER().call(
        block_identifier=block
    )

    provider = w3.eth.contract(
        address=provider_address,
        abi=PROVIDER_ABI,
    )

    data_provider_address = (
        provider.functions.getPoolDataProvider().call(
            block_identifier=block
        )
    )

    data_provider = w3.eth.contract(
        address=data_provider_address,
        abi=DATA_ABI,
    )

    token_cache = {}
    passed = 0
    failed = 0
    rpc_errors = 0

    zero_address = "0x0000000000000000000000000000000000000000"

    for row in affected.itertuples():
        try:
            asset = Web3.to_checksum_address(row.underlying)
            wallet = Web3.to_checksum_address(row.wallet)

            if asset not in token_cache:
                _, stable_token, variable_token = (
                    data_provider.functions
                    .getReserveTokensAddresses(asset)
                    .call(block_identifier=block)
                )
                token_cache[asset] = (stable_token, variable_token)

            stable_address, variable_address = token_cache[asset]

            if variable_address.lower() == zero_address:
                raise RuntimeError("Missing variable debt token")

            variable = w3.eth.contract(
                address=variable_address,
                abi=DEBT_ABI,
            )

            variable_balance = variable.functions.balanceOf(
                wallet
            ).call(block_identifier=block)

            scaled_balance = variable.functions.scaledBalanceOf(
                wallet
            ).call(block_identifier=block)

            stable_balance = 0

            if stable_address.lower() != zero_address:
                stable = w3.eth.contract(
                    address=stable_address,
                    abi=DEBT_ABI,
                )
                stable_balance = stable.functions.balanceOf(
                    wallet
                ).call(block_identifier=block)

            if is_verified_zero(
                variable_balance, scaled_balance, stable_balance
            ):
                passed += 1
            else:
                failed += 1
                print(
                    f"MISMATCH wallet={row.wallet} asset={row.symbol} "
                    f"variable={variable_balance} "
                    f"scaled={scaled_balance} "
                    f"stable={stable_balance}"
                )

        except Exception as exc:
            rpc_errors += 1
            print(
                f"RPC ERROR wallet={row.wallet} asset={row.symbol}: "
                f"{type(exc).__name__}: {exc}"
            )

    print("\nHISTORICAL DEBT AUDIT")
    print(f"Snapshot block: {block}")
    print(f"Zero debt verified: {passed}")
    print(f"Nonzero debt mismatches: {failed}")
    print(f"RPC errors: {rpc_errors}")

    if failed or rpc_errors:
        raise RuntimeError(
            "Historical debt audit FAILED or INCOMPLETE"
        )

    if passed != len(affected):
        raise RuntimeError("Audit coverage mismatch")

    print("PASS: All sampled corrections verified at snapshot block")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", type=int, required=True)
    parser.add_argument("--top-reserves", type=int, default=10)
    parser.add_argument("--borrowers-per-reserve", type=int, default=50)
    args = parser.parse_args()

    audit(
        args.block,
        args.top_reserves,
        args.borrowers_per_reserve,
    )
