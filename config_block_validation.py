def validate_liquidation_config_blocks(
    *,
    snapshot_block,
    reserve_configs,
    emode_configs,
):
    """Reject missing or cross-block liquidation configurations."""

    if (
        isinstance(snapshot_block, bool)
        or not isinstance(snapshot_block, int)
        or snapshot_block < 0
    ):
        raise ValueError("Invalid liquidation snapshot block")

    if not reserve_configs:
        raise RuntimeError("No reserve configurations returned")

    for name, configs in (
        ("reserve", reserve_configs),
        ("eMode", emode_configs),
    ):
        for identifier, config in configs.items():
            actual = config.get("block_number")

            if actual != snapshot_block or isinstance(actual, bool):
                raise RuntimeError(
                    f"{name} configuration block mismatch "
                    f"for {identifier}: expected {snapshot_block}, "
                    f"received {actual}"
                )

    return {
        "snapshot_block": snapshot_block,
        "config_blocks_aligned": True,
        "reserves_checked": len(reserve_configs),
        "emode_categories_checked": len(emode_configs),
    }
