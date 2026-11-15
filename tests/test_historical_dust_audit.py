from audit_negative_dust import is_verified_zero


def test_zero_debt_verified():
    assert is_verified_zero(0, 0, 0)


def test_variable_debt_mismatch():
    assert not is_verified_zero(1, 0, 0)


def test_scaled_debt_mismatch():
    assert not is_verified_zero(0, 1, 0)


def test_stable_debt_mismatch():
    assert not is_verified_zero(0, 0, 1)
