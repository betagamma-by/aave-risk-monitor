"""Fail-closed verification and normalization of negative aToken dust."""

from decimal import Decimal, InvalidOperation

from web3 import Web3

from data_integrity_errors import DataIntegrityError
from historical_debt_verification import HistoricalDebtReader
from audit_negative_dust import DEBT_ABI


def _amount(value):
    try:
        amount = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise DataIntegrityError("Invalid collateral source balance") from exc

    if not amount.is_finite():
        raise DataIntegrityError("Non-finite collateral source balance")

    return amount


class HistoricalCollateralReader:
    def __init__(self, block):
        self.block = block
        self.base = HistoricalDebtReader(block)
        self.token_cache = {}

    def read(self, wallet, underlying):
        asset = Web3.to_checksum_address(underlying)
        owner = Web3.to_checksum_address(wallet)

        if asset not in self.token_cache:
            addresses = (
                self.base.data_provider.functions
                .getReserveTokensAddresses(asset)
                .call(block_identifier=self.block)
            )
            if len(addresses) != 3:
                raise RuntimeError("Invalid reserve token addresses")

            atoken_address = addresses[0]
            if int(atoken_address, 16) == 0:
                raise RuntimeError("Missing aToken address")

            self.token_cache[asset] = atoken_address

        token = self.base.w3.eth.contract(
            address=self.token_cache[asset],
            abi=DEBT_ABI,
        )

        balance = token.functions.balanceOf(owner).call(
            block_identifier=self.block
        )
        scaled = token.functions.scaledBalanceOf(owner).call(
            block_identifier=self.block
        )
        return balance, scaled


def normalize_verified_negative_collateral(
    raw, block_identifier, reader=None
):
    """Only correct bounded negative subgraph balances verified zero on-chain."""

    result = raw.copy()
    affected = []

    for idx, row in result.iterrows():
        scaled = _amount(row["scaled_atoken_raw"])
        balance = _amount(row["atoken_balance_raw"])

        if scaled >= 0 and balance >= 0:
            continue

        # Raw token units, NOT whole tokens.
        # Conservative diagnostic bounds, not a blanket rounding rule.
        if not (
            Decimal("-10") <= scaled <= Decimal("10")
            and Decimal("-20") <= balance <= Decimal("20")
        ):
            raise DataIntegrityError(
                "Untrusted negative collateral: "
                f"wallet={row['wallet']}, asset={row['symbol']}, "
                f"scaled={scaled}, balance={balance}"
            )

        affected.append((idx, row))

    if not affected:
        return result

    if (
        isinstance(block_identifier, bool)
        or not isinstance(block_identifier, int)
        or block_identifier < 0
    ):
        raise DataIntegrityError(
            "Historical block required to verify negative collateral"
        )

    if reader is None:
        try:
            reader = HistoricalCollateralReader(block_identifier).read
        except Exception as exc:
            raise DataIntegrityError(
                f"Collateral verification RPC initialization failed: {exc}"
            ) from exc

    for idx, row in affected:
        try:
            balances = reader(row["wallet"], row["underlying"])

            if (
                len(balances) != 2
                or not all(
                    isinstance(x, int)
                    and not isinstance(x, bool)
                    and x >= 0
                    for x in balances
                )
            ):
                raise RuntimeError("Invalid on-chain aToken response")

            if balances != (0, 0):
                raise RuntimeError(
                    f"On-chain collateral is nonzero: {balances}"
                )

        except Exception as exc:
            raise DataIntegrityError(
                "Historical collateral verification FAILED: "
                f"wallet={row['wallet']}, asset={row['symbol']}, "
                f"block={block_identifier}: {exc}"
            ) from exc

        result.at[idx, "scaled_atoken_raw"] = "0"
        result.at[idx, "atoken_balance_raw"] = "0"

    print(
        f"F17: Verified and normalized {len(affected)} "
        f"negative collateral-dust positions "
        f"against Ethereum block {block_identifier}"
    )

    return result
