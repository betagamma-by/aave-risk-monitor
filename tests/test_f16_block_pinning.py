import inspect

from reserve_config_fetcher import fetch_reserve_configs
from emode_fetcher import fetch_emode_configs


def test_reserve_fetcher_accepts_block_identifier():
    params = inspect.signature(fetch_reserve_configs).parameters
    assert "block_identifier" in params
    assert params["block_identifier"].default is None


def test_emode_fetcher_accepts_block_identifier():
    params = inspect.signature(fetch_emode_configs).parameters
    assert "block_identifier" in params
    assert params["block_identifier"].default is None
