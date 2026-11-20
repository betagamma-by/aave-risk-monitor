from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from current_wallet_verification import fetch_current_wallet_account


def mocked_web3(values, chain_id=1):
    w3 = MagicMock()
    w3.eth.chain_id = chain_id
    w3.eth.block_number = 12345
    w3.eth.contract.return_value.functions.BASE_CURRENCY_UNIT.return_value.call.return_value = 10**8
    w3.eth.contract.return_value.functions.getUserAccountData \
        .return_value.call.return_value = values
    return w3


@patch("current_wallet_verification.Web3")
def test_current_wallet_values_and_block_pinning(mock_web3):
    w3 = mocked_web3((
        6000 * 10**8,
        3000 * 10**8,
        1800 * 10**8,
        8000,
        7500,
        16 * 10**17,
    ))
    mock_web3.return_value = w3
    mock_web3.to_checksum_address.side_effect = lambda x: x

    result = fetch_current_wallet_account(
        "0xabc", rpc_url="http://test", pool_address="0xpool"
    )

    assert result["block_number"] == 12345
    assert str(result["collateral_usd"]) == "6000"
    assert str(result["debt_usd"]) == "3000"
    assert result["health_factor"] == Decimal("1.6")
    assert result["ltv_pct"] == 75

    call = (
        w3.eth.contract.return_value.functions
        .getUserAccountData.return_value.call
    )
    call.assert_called_once_with(block_identifier=12345)


@patch("current_wallet_verification.Web3")
def test_no_debt_has_no_finite_hf(mock_web3):
    mock_web3.return_value = mocked_web3((
        1000 * 10**8, 0, 750 * 10**8,
        8000, 7500, 2**256 - 1,
    ))
    mock_web3.to_checksum_address.side_effect = lambda x: x

    result = fetch_current_wallet_account(
        "0xabc", rpc_url="http://test", pool_address="0xpool"
    )

    assert result["health_factor"] is None
    assert result["has_debt"] is False


@patch("current_wallet_verification.Web3")
def test_wrong_network_rejected(mock_web3):
    mock_web3.return_value = mocked_web3((), chain_id=137)

    with pytest.raises(RuntimeError, match="Ethereum mainnet"):
        fetch_current_wallet_account(
            "0xabc", rpc_url="http://test", pool_address="0xpool"
        )

@pytest.fixture(autouse=True)
def mock_oracle_address(monkeypatch):
    monkeypatch.setenv(
        "AAVE_ORACLE_ADDRESS",
        "0x0000000000000000000000000000000000000002",
    )


@patch("current_wallet_verification.Web3")
def test_unexpected_oracle_unit_rejected(mock_web3):
    w3 = mocked_web3((0, 0, 0, 0, 0, 0))
    w3.eth.contract.return_value.functions.BASE_CURRENCY_UNIT.return_value.call.return_value = 10**18
    mock_web3.return_value = w3
    mock_web3.to_checksum_address.side_effect = lambda x: x

    with pytest.raises(RuntimeError, match="Unexpected Aave Ethereum USD"):
        fetch_current_wallet_account(
            "0xabc", rpc_url="http://test", pool_address="0xpool"
        )


@patch("current_wallet_verification.Web3")
def test_oracle_unit_is_pinned_to_account_block(mock_web3):
    w3 = mocked_web3((100 * 10**8, 50 * 10**8, 0, 8000, 7500, 16 * 10**17))
    mock_web3.return_value = w3
    mock_web3.to_checksum_address.side_effect = lambda x: x

    result = fetch_current_wallet_account(
        "0xabc",
        rpc_url="http://test",
        pool_address="0xpool",
        block_identifier=12345,
    )

    assert result["collateral_usd"] == 100
    assert result["debt_usd"] == 50

    w3.eth.contract.return_value.functions.BASE_CURRENCY_UNIT.return_value.call.assert_called_once_with(
        block_identifier=12345
    )
