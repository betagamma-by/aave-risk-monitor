"""Compare monitor HF with historical and current Aave Pool HF."""

from decimal import Decimal


def compare_wallet_health_factors(
    monitor_hf,
    historical_onchain_hf,
    current_onchain_hf,
):
    def number(value):
        if value is None:
            return None
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError("Invalid Health Factor")
        return result

    monitor = number(monitor_hf)
    historical = number(historical_onchain_hf)
    current = number(current_onchain_hf)

    model_delta = (
        monitor - historical
        if monitor is not None and historical is not None
        else None
    )

    chain_delta = (
        current - historical
        if current is not None and historical is not None
        else None
    )

    model_error_pct = (
        abs(model_delta) / historical * 100
        if model_delta is not None and historical > 0
        else None
    )

    return {
        "monitor_hf": monitor,
        "historical_onchain_hf": historical,
        "current_onchain_hf": current,
        "model_delta": model_delta,
        "model_error_pct": model_error_pct,
        "chain_delta": chain_delta,
    }
