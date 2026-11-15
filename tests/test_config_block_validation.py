import pytest

from config_block_validation import validate_liquidation_config_blocks


def validate(reserves, emodes=None, block=12345):
    return validate_liquidation_config_blocks(
        snapshot_block=block,
        reserve_configs=reserves,
        emode_configs={} if emodes is None else emodes,
    )


def test_all_configurations_aligned():
    result = validate(
        {
            "0xweth": {"block_number": 12345},
            "0xusdc": {"block_number": 12345},
        },
        {
            1: {"block_number": 12345},
        },
    )

    assert result["config_blocks_aligned"] is True
    assert result["reserves_checked"] == 2
    assert result["emode_categories_checked"] == 1


def test_reserve_block_mismatch_rejected():
    with pytest.raises(RuntimeError, match="reserve configuration block mismatch"):
        validate({
            "0xweth": {"block_number": 12346},
        })


def test_emode_block_mismatch_rejected():
    with pytest.raises(RuntimeError, match="eMode configuration block mismatch"):
        validate(
            {"0xweth": {"block_number": 12345}},
            {1: {"block_number": 12346}},
        )


def test_missing_block_metadata_rejected():
    with pytest.raises(RuntimeError, match="block mismatch"):
        validate({"0xweth": {}})


def test_empty_emode_allowed():
    result = validate({"0xweth": {"block_number": 12345}})
    assert result["emode_categories_checked"] == 0


def test_no_reserve_configurations_rejected():
    with pytest.raises(RuntimeError, match="No reserve"):
        validate({})


@pytest.mark.parametrize("block", [-1, True, None, "12345"])
def test_invalid_snapshot_block_rejected(block):
    with pytest.raises(ValueError, match="Invalid"):
        validate(
            {"0xweth": {"block_number": 12345}},
            block=block,
        )
