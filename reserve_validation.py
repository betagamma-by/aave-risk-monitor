
"""Validate subgraph reserve metadata against Aave on-chain settings."""


def validate_reserve_metadata(prepared_raw, configs):
    """Return mismatches between borrower metadata and on-chain reserves."""
    required = {"underlying", "symbol", "decimals", "base_lt_bps"}
    missing_columns = required - set(prepared_raw.columns)

    if missing_columns:
        raise ValueError(
            f"Missing reserve fields: {sorted(missing_columns)}"
        )

    issues = []

    for row in prepared_raw[
        ["underlying", "symbol", "decimals", "base_lt_bps"]
    ].drop_duplicates().itertuples(index=False):

        address = str(row.underlying).lower()
        config = configs.get(address)

        if config is None:
            issues.append({
                "asset": row.symbol,
                "address": address,
                "issue": "Missing on-chain configuration",
            })
            continue

        if int(row.decimals) != config["decimals"]:
            issues.append({
                "asset": row.symbol,
                "address": address,
                "issue": "Token decimals mismatch",
            })

        if int(row.base_lt_bps) != config["liquidation_threshold_bps"]:
            issues.append({
                "asset": row.symbol,
                "address": address,
                "issue": "Base liquidation threshold mismatch",
            })

    return issues
