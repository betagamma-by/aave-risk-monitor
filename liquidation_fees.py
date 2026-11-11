"""Indicative Aave liquidation protocol-fee calculations."""

from decimal import Decimal


def estimate_liquidation_fee(
    *, repayable_debt_usd, gross_collateral_seized_usd,
    protocol_fee_bps
):
    debt = Decimal(str(repayable_debt_usd))
    seized = Decimal(str(gross_collateral_seized_usd))
    fee_bps = Decimal(str(protocol_fee_bps))

    if not all(x.is_finite() for x in (debt, seized, fee_bps)):
        raise ValueError("All inputs must be finite")

    if debt < 0 or seized < debt or not 0 <= fee_bps <= 10000:
        raise ValueError("Invalid liquidation fee inputs")

    gross_bonus = seized - debt
    protocol_fee = gross_bonus * fee_bps / Decimal(10000)
    net_collateral = seized - protocol_fee

    return {
        "gross_bonus_usd": gross_bonus,
        "protocol_fee_usd": protocol_fee,
        "liquidator_collateral_usd": net_collateral,
        "net_bonus_before_costs_usd": net_collateral - debt,
    }
