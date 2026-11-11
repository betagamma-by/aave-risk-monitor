
"""Helpers for Aave V3 eMode collateral eligibility."""


def collateral_allowed(bitmap: int, reserve_id: int) -> bool:
    if isinstance(bitmap, bool) or not isinstance(bitmap, int):
        raise ValueError("Bitmap must be an integer")
    if isinstance(reserve_id, bool) or not isinstance(reserve_id, int):
        raise ValueError("Reserve ID must be an integer")
    if bitmap < 0 or bitmap >= 2**128:
        raise ValueError("Invalid collateral bitmap")
    if not 0 <= reserve_id < 128:
        raise ValueError("Reserve ID outside bitmap range")

    return bool(bitmap & (1 << reserve_id))
