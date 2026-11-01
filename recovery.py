def load_with_fallback(load_live, load_snapshot, top_reserves, borrowers_per_reserve):
    try:
        live_result = load_live(top_reserves, borrowers_per_reserve)

        # Support both original callers and F13 callers.
        if len(live_result) == 5:
            positions, stats, fetched_at, freshness, scenario_inputs = live_result
        else:
            positions, stats, fetched_at, freshness = live_result
            scenario_inputs = None

        return positions, stats, fetched_at, freshness, "live", scenario_inputs

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

            return positions, stats, captured_at, freshness, "snapshot", None

        except Exception as snapshot_error:
            raise RuntimeError(
                "Both live Aave data and GitHub snapshot recovery failed. "
                f"Live error: {type(live_error).__name__}; "
                f"snapshot error: {type(snapshot_error).__name__}"
            ) from snapshot_error
