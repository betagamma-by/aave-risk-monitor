def select_snapshot_context(graph_meta, w3):
    """Select the latest indexed block also available from this RPC."""

    if graph_meta["hasIndexingErrors"]:
        raise RuntimeError("Subgraph reports indexing errors")

    graph_block = int(graph_meta["block"]["number"])
    chain_block = int(w3.eth.block_number)

    if graph_block < 0 or graph_block > chain_block:
        raise RuntimeError(
            "Subgraph and Ethereum RPC block heights are inconsistent"
        )

    block = w3.eth.get_block(graph_block)

    if block is None:
        raise RuntimeError("Selected Ethereum block unavailable")

    return {
        "snapshot_block": graph_block,
        "snapshot_timestamp": int(block["timestamp"]),
        "chain_block": chain_block,
        "graph_block": graph_block,
    }
