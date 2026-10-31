def load_with_fallback(load_live, load_snapshot, top_reserves, borrowers_per_reserve):
    try:
        positions, stats, fetched_at, freshness = load_live(
            top_reserves, borrowers_per_reserve
        )
        return positions, stats, fetched_at, freshness, "live"

    except Exception as live_error:
        try:
            positions, stats, captured_at, metadata = load_snapshot()

            stats = stats.copy()
            stats["price_source"] = metadata["price_source"]

            freshness = {
                "chain_block": metadata.get("chain_block"),
                "graph_block": metadata.get("graph_block"),
                "lag_blocks": metadata.get("lag_blocks"),
                "indexing_errors": metadata.get("indexing_errors"),
            }

            return positions, stats, captured_at, freshness, "snapshot"

        except Exception as snapshot_error:
            raise RuntimeError(
                "Both live Aave data and GitHub snapshot recovery failed. "
                f"Live error: {type(live_error).__name__}; "
                f"snapshot error: {type(snapshot_error).__name__}"
            ) from snapshot_error