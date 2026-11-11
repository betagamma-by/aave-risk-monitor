from liquidation_constraints import check_liquidation_dust


def test_both_remain_above_threshold():
    assert check_liquidation_dust(5000, 2000)["passes_dust_check"]


def test_full_debt_repayment():
    assert check_liquidation_dust(0, 500)["passes_dust_check"]


def test_full_collateral_seizure():
    assert check_liquidation_dust(500, 0)["passes_dust_check"]


def test_partial_liquidation_leaving_dust():
    result = check_liquidation_dust(500, 500)
    assert not result["passes_dust_check"]
