
"""Decode Aave V3 Pool.getConfiguration(asset) reserve parameters.

Uses the documented Aave V3 ReserveConfigurationMap bit layout.
Does not perform network requests.
"""

from decimal import Decimal

BPS = Decimal("10000")


def decode_reserve_configuration(packed):
    """Decode a uint256 reserve configuration value."""
    if not isinstance(packed, int) or isinstance(packed, bool):
        raise ValueError("Configuration must be an integer")

    if packed < 0 or packed >= 2**256:
        raise ValueError("Configuration exceeds uint256 range")

    def bits(start, width):
        return (packed >> start) & ((1 << width) - 1)

    threshold_bps = bits(16, 16)
    bonus_bps = bits(32, 16)
    decimals = bits(48, 8)
    protocol_fee_bps = bits(152, 16)

    if threshold_bps == 0:
        if bonus_bps != 0:
            raise ValueError("Disabled collateral must have zero liquidation bonus")
    elif bonus_bps <= 10000:
        raise ValueError("Enabled collateral must have a positive liquidation bonus")
    if protocol_fee_bps > 10000:
        raise ValueError("Invalid liquidation protocol fee")
    if threshold_bps > 10000:
        raise ValueError("Invalid liquidation threshold")

    return {
        "liquidation_threshold_bps": threshold_bps,
        "liquidation_bonus_bps": bonus_bps,
        "liquidation_bonus_pct": (
            (Decimal(bonus_bps) - BPS) / BPS
            if threshold_bps > 0 else Decimal("0")
        ),
        "collateral_liquidation_enabled": threshold_bps > 0,
        "liquidation_protocol_fee_bps": protocol_fee_bps,
        "liquidation_protocol_fee_pct": (
            Decimal(protocol_fee_bps) / BPS
        ),
        "decimals": decimals,
        "is_active": bool(bits(56, 1)),
        "is_paused": bool(bits(60, 1)),
    }
