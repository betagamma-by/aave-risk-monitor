"""Control access to historical liquidation-exposure calculations."""


def exposure_available(
    data_source,
    scenario_inputs_present,
    snapshot_block,
    historical_debt_verified,
):
    return (
        data_source == "live"
        and scenario_inputs_present is True
        and historical_debt_verified is True
        and isinstance(snapshot_block, int)
        and not isinstance(snapshot_block, bool)
        and snapshot_block >= 0
    )
