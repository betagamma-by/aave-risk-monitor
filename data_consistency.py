def evaluate_data_freshness(
    *,
    chain_block: int,
    graph_block: int,
    indexing_errors: bool,
    max_lag_blocks: int = 20,
) -> dict:
    """Evaluate indexing freshness, not cross-source block consistency."""
    if chain_block < 0 or graph_block < 0:
        raise ValueError("Block numbers cannot be negative")

    if max_lag_blocks < 0:
        raise ValueError("Maximum lag cannot be negative")

    lag = chain_block - graph_block

    if indexing_errors:
        status = "unreliable"
    elif lag < 0:
        status = "unreliable"
    elif lag > max_lag_blocks:
        status = "delayed"
    else:
        status = "healthy"

    return {
        "status": status,
        "chain_block": chain_block,
        "graph_block": graph_block,
        "lag_blocks": lag,
        "indexing_errors": indexing_errors,
        "block_consistent": False,
    }
