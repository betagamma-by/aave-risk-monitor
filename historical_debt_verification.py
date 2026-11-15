"""Fail-closed historical verification of negative subgraph debt dust."""

import os
from decimal import Decimal

from web3 import Web3

from audit_negative_dust import (
    POOL_ABI, PROVIDER_ABI, DATA_ABI, DEBT_ABI,
    is_verified_zero,
)


class HistoricalDebtReader:
    def __init__(self, block):
        self.block = block
        self.w3 = Web3(Web3.HTTPProvider(
            os.environ["ETH_RPC_URL"],
            request_kwargs={"timeout": 30},
        ))

        if self.w3.eth.chain_id != 1:
            raise RuntimeError("Historical debt verification requires Ethereum mainnet")

        self.w3.eth.get_block(block)

        pool = self.w3.eth.contract(
            address=Web3.to_checksum_address(
                os.environ["AAVE_POOL_ADDRESS"]
            ),
            abi=POOL_ABI,
        )
        provider_address = pool.functions.ADDRESSES_PROVIDER().call(
            block_identifier=block
        )
        provider = self.w3.eth.contract(
            address=provider_address, abi=PROVIDER_ABI
        )
        data_address = provider.functions.getPoolDataProvider().call(
            block_identifier=block
        )
        self.data_provider = self.w3.eth.contract(
            address=data_address, abi=DATA_ABI
        )
        self.token_cache = {}

    def read(self, wallet, underlying):
        asset = Web3.to_checksum_address(underlying)
        owner = Web3.to_checksum_address(wallet)

        if asset not in self.token_cache:
            addresses = (
                self.data_provider.functions
                .getReserveTokensAddresses(asset)
                .call(block_identifier=self.block)
            )
            self.token_cache[asset] = addresses[1:3]

        stable_address, variable_address = self.token_cache[asset]
        zero = "0x0000000000000000000000000000000000000000"

        if variable_address.lower() == zero:
            raise RuntimeError("Missing variable debt token")

        variable = self.w3.eth.contract(
            address=variable_address, abi=DEBT_ABI
        )
        variable_balance = variable.functions.balanceOf(owner).call(
            block_identifier=self.block
        )
        scaled_balance = variable.functions.scaledBalanceOf(owner).call(
            block_identifier=self.block
        )

        stable_balance = 0
        if stable_address.lower() != zero:
            stable = self.w3.eth.contract(
                address=stable_address, abi=DEBT_ABI
            )
            stable_balance = stable.functions.balanceOf(owner).call(
                block_identifier=self.block
            )

        return variable_balance, scaled_balance, stable_balance


def verify_negative_debt_at_block(raw, block_identifier, reader=None):
    """Require confirmed zero on-chain debt for every dust correction."""
    if (
        isinstance(block_identifier, bool)
        or not isinstance(block_identifier, int)
        or block_identifier < 0
    ):
        raise ValueError("Valid historical snapshot block required")

    affected = []

    for row in raw.itertuples(index=False):
        scaled = Decimal(str(row.scaled_vdebt_raw))
        if not scaled.is_finite():
            raise ValueError("Non-finite scaled variable debt")

        if scaled >= 0:
            continue

        stable = Decimal(str(row.stable_debt_raw))
        total = Decimal(str(row.debt_raw))

        if not (
            stable.is_finite()
            and total.is_finite()
            and Decimal("-10") <= scaled < 0
            and stable == 0
            and Decimal("-20") <= total <= Decimal("20")
        ):
            raise RuntimeError(
                f"Untrusted negative debt: {row.wallet} {row.symbol}"
            )

        affected.append(row)

    if not affected:
        return 0

    if reader is None:
        reader = HistoricalDebtReader(block_identifier).read

    for row in affected:
        try:
            balances = reader(row.wallet, row.underlying)

            if len(balances) != 3 or not all(
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
                for value in balances
            ):
                raise RuntimeError("Invalid historical debt response")

            if not is_verified_zero(*balances):
                raise RuntimeError(
                    f"On-chain debt is nonzero: {balances}"
                )

        except Exception as exc:
            raise RuntimeError(
                f"Historical debt verification FAILED: "
                f"wallet={row.wallet}, asset={row.symbol}, "
                f"block={block_identifier}: {exc}"
            ) from exc

    print(
        f"F16: Verified {len(affected)} negative debt-dust "
        f"positions against Ethereum block {block_identifier}"
    )
    return len(affected)
