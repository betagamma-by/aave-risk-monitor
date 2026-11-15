import pytest

from subgraph_block import pin_subgraph_query


@pytest.mark.parametrize(
    "entity",
    ["reserves", "users", "userReserves"],
)
def test_query_is_pinned(entity):
    query = f"{{ {entity}(first: 10) {{ id }} }}"
    result = pin_subgraph_query(query, 12345)

    assert (
        f"{entity}(block: {{ number: 12345 }}, first: 10)"
        in result
    )


def test_nested_fields_preserved():
    query = """{
        users(first: 10) {
            id
            reserves { currentTotalDebt }
        }
    }"""

    result = pin_subgraph_query(query, 12345)

    assert "reserves { currentTotalDebt }" in result
    assert result.count("block:") == 1


@pytest.mark.parametrize("block", [-1, True, "12345"])
def test_invalid_block_rejected(block):
    with pytest.raises(ValueError):
        pin_subgraph_query(
            "{ users(first: 10) { id } }",
            block,
        )


def test_unknown_query_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        pin_subgraph_query(
            "{ somethingElse(first: 10) { id } }",
            12345,
        )
