from unittest.mock import Mock
import pytest

from snapshot_context import select_snapshot_context


def make_rpc(head=1005):
    w3 = Mock()
    w3.eth.block_number = head
    w3.eth.get_block.return_value = {"timestamp": 1700000000}
    return w3


def test_select_latest_indexed_block():
    w3 = make_rpc()

    result = select_snapshot_context(
        {
            "block": {"number": 1004},
            "hasIndexingErrors": False,
        },
        w3,
    )

    assert result["snapshot_block"] == 1004
    assert result["snapshot_timestamp"] == 1700000000
    w3.eth.get_block.assert_called_once_with(1004)


def test_indexing_errors_rejected():
    with pytest.raises(RuntimeError, match="indexing errors"):
        select_snapshot_context(
            {
                "block": {"number": 1004},
                "hasIndexingErrors": True,
            },
            make_rpc(),
        )


def test_subgraph_ahead_rejected():
    with pytest.raises(RuntimeError, match="inconsistent"):
        select_snapshot_context(
            {
                "block": {"number": 1006},
                "hasIndexingErrors": False,
            },
            make_rpc(),
        )
