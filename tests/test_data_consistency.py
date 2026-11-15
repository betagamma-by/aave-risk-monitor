import pytest

from data_consistency import evaluate_data_freshness


def test_healthy_indexing():
    result = evaluate_data_freshness(
        chain_block=1005,
        graph_block=1004,
        indexing_errors=False,
    )
    assert result["status"] == "healthy"
    assert result["block_consistent"] is False


def test_delayed_indexing():
    result = evaluate_data_freshness(
        chain_block=1050,
        graph_block=1002,
        indexing_errors=False,
    )
    assert result["status"] == "delayed"
    assert result["lag_blocks"] == 48


def test_indexing_error():
    result = evaluate_data_freshness(
        chain_block=1005,
        graph_block=1005,
        indexing_errors=True,
    )
    assert result["status"] == "unreliable"


def test_subgraph_ahead_of_rpc():
    result = evaluate_data_freshness(
        chain_block=1004,
        graph_block=1005,
        indexing_errors=False,
    )
    assert result["status"] == "unreliable"


def test_invalid_block():
    with pytest.raises(ValueError):
        evaluate_data_freshness(
            chain_block=-1,
            graph_block=1005,
            indexing_errors=False,
        )
