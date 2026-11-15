import re

ROOT_QUERY = re.compile(
    r"^(\s*\{\s*)(reserves|users|userReserves)(\s*\()",
    re.DOTALL,
)


def pin_subgraph_query(query: str, block_identifier: int) -> str:
    """Pin supported Aave entity queries to an Ethereum block."""
    if (
        isinstance(block_identifier, bool)
        or not isinstance(block_identifier, int)
        or block_identifier < 0
    ):
        raise ValueError("block_identifier must be a non-negative integer")

    match = ROOT_QUERY.match(query)
    if match is None:
        raise ValueError(
            "Unsupported GraphQL query for block pinning; "
            "refusing an unpinned read"
        )

    start = match.end()
    argument = f"block: {{ number: {block_identifier} }}, "

    return query[:start] + argument + query[start:]
