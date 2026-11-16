"""Input validation, conditioning checks and classification status tests."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from binomial_arbitrage import MarketParams, MarketStatus, Tolerances, ValidationError, classify_inputs, classify_market
from binomial_arbitrage.payoffs import ClaimSpec
from binomial_arbitrage.validation import to_decimal, validate_cash_payout, validate_strike


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, "nan", "inf", None, True, "abc", [1]])
def test_non_finite_or_non_numeric_inputs_rejected(bad):
    with pytest.raises(ValidationError):
        MarketParams.create(bad, 1.1, 0.9, 0.01)


@pytest.mark.parametrize("field", ["u", "d", "r"])
def test_non_finite_parameter_rejected_in_each_position(field):
    kwargs = {"S0": 100, "u": 1.1, "d": 0.9, "r": 0.01}
    kwargs[field] = math.nan
    with pytest.raises(ValidationError):
        MarketParams.create(**kwargs)


@pytest.mark.parametrize("S0", [0, -1, -1e-12])
def test_nonpositive_S0_rejected(S0):
    with pytest.raises(ValidationError, match="S0"):
        MarketParams.create(S0, 1.1, 0.9, 0.01)


@pytest.mark.parametrize("u,d", [(0.9, 1.1), (1.1, 0.0), (1.1, -0.5), (0.5, 0.6)])
def test_invalid_multipliers_rejected(u, d):
    with pytest.raises(ValidationError):
        MarketParams.create(100, u, d, 0.01)


def test_u_equal_d_rejected_as_degenerate():
    with pytest.raises(ValidationError, match="degenerate"):
        MarketParams.create(100, 1.05, 1.05, 0.02)


@pytest.mark.parametrize("r", [-1, -1.5, "-1.0"])
def test_r_le_minus_one_rejected(r):
    with pytest.raises(ValidationError, match="r must be > -1"):
        MarketParams.create(100, 1.1, 0.9, r)


def test_extra_restrictions_not_required():
    # u < 1, d > 1 and r < 0 are all acceptable in the generalized model.
    MarketParams.create(100, 0.99, 0.85, -0.05)
    MarketParams.create(100, 1.15, 1.01, 0.05)
    MarketParams.create(100, 1.05, 0.90, -0.03)


def test_negative_strike_rejected_zero_allowed():
    with pytest.raises(ValidationError, match="K must be >= 0"):
        validate_strike(-0.01)
    assert validate_strike(0) == Decimal(0)
    with pytest.raises(ValidationError):
        ClaimSpec.from_mapping({"type": "put", "K": -5})


def test_negative_digital_payout_rejected():
    with pytest.raises(ValidationError, match="cash_payout"):
        validate_cash_payout(-1)
    with pytest.raises(ValidationError):
        ClaimSpec.from_mapping({"type": "digital", "K": 100, "cash_payout": -2})
    assert validate_cash_payout(0) == Decimal(0)


def test_unknown_claim_type_rejected():
    with pytest.raises(ValidationError):
        ClaimSpec.from_mapping({"type": "american_put", "K": 100})


def test_float_conversion_uses_shortest_repr():
    assert to_decimal(0.02, "r") == Decimal("0.02")
    assert to_decimal(Decimal("1.019999999999"), "d") == Decimal("1.019999999999")


def test_ill_conditioned_separation_rejected():
    with pytest.raises(ValidationError, match="ill-conditioned"):
        MarketParams.create(100, Decimal("1.0200000000001"), Decimal("1.02"), 0.02)


def test_narrow_separation_produces_warning_but_runs():
    params = MarketParams.create(100, Decimal("1.0200005"), Decimal("1.0199995"), Decimal("0.02"))
    assert any(w.startswith("narrow_state_separation") for w in params.warnings)
    assert classify_market(params).status is MarketStatus.ARBITRAGE_FREE


def test_well_separated_market_has_no_conditioning_warning(baseline_params):
    assert baseline_params.warnings == ()


def test_conditioning_thresholds_are_configurable():
    tight = Tolerances(min_relative_state_separation=0.5)
    with pytest.raises(ValidationError, match="ill-conditioned"):
        MarketParams.create(100, 1.12, 0.92, 0.02, tight)


def test_tolerances_reject_unknown_keys_and_negatives():
    with pytest.raises(ValidationError):
        Tolerances.from_mapping({"not_a_tolerance": 1.0})
    with pytest.raises(ValidationError):
        Tolerances(payoff_abs_tol=-1.0)


def test_classify_inputs_reports_invalid_without_raising():
    params, cls = classify_inputs(100, 1.05, 1.05, 0.02)
    assert params is None
    assert cls.status is MarketStatus.INVALID_INPUT
    assert "degenerate" in cls.message


def test_invalid_input_distinct_from_arbitrage_market():
    params, cls = classify_inputs(100, 1.05, 0.98, 0.10)  # valid inputs, R > u
    assert params is not None
    assert cls.status is MarketStatus.ARBITRAGE_R_GE_U


@pytest.mark.parametrize(
    "u,d,r,expected",
    [
        ("1.12", "0.92", "0.02", MarketStatus.ARBITRAGE_FREE),
        ("1.25", "1.05", "0.02", MarketStatus.ARBITRAGE_R_LE_D),
        ("1.05", "0.98", "0.10", MarketStatus.ARBITRAGE_R_GE_U),
        ("1.12", "1.02", "0.02", MarketStatus.ARBITRAGE_R_LE_D),
        ("1.12", "0.92", "0.12", MarketStatus.ARBITRAGE_R_GE_U),
        ("1.12", "1.019999999999", "0.02", MarketStatus.NEAR_BOUNDARY_UNRESOLVED),
        ("1.12", "1.020000000001", "0.02", MarketStatus.NEAR_BOUNDARY_UNRESOLVED),
    ],
)
def test_classification_statuses(u, d, r, expected):
    params = MarketParams.create(100, Decimal(u), Decimal(d), Decimal(r))
    assert classify_market(params).status is expected


def test_exact_equality_is_arbitrage_not_unresolved():
    eq_d = classify_market(MarketParams.create(100, Decimal("1.12"), Decimal("1.02"), Decimal("0.02")))
    eq_u = classify_market(MarketParams.create(100, Decimal("1.12"), Decimal("0.92"), Decimal("0.12")))
    assert eq_d.exact_boundary == "R_equals_d" and eq_d.q_candidate == 0.0
    assert eq_u.exact_boundary == "R_equals_u" and eq_u.q_candidate == 1.0
    assert not eq_d.is_arbitrage_free and not eq_u.is_arbitrage_free


def test_float_inputs_detect_exact_boundary_via_decimal_repr():
    # 1 + 0.02 in binary floating point is not exactly the double 1.02, but the
    # decimal interpretation used by the package makes R == d exactly.
    cls = classify_market(MarketParams.create(100, 1.12, 1.02, 0.02))
    assert cls.exact_boundary == "R_equals_d"


def test_q_candidate_not_clipped_outside_interval():
    cls = classify_market(MarketParams.create(100, Decimal("1.05"), Decimal("0.98"), Decimal("0.10")))
    assert cls.q_candidate > 1.0  # (1.10 - 0.98)/0.07 = 1.714...
    assert cls.q_candidate == pytest.approx(0.12 / 0.07, rel=1e-12)
    assert cls.to_dict()["q_is_valid_risk_neutral_probability"] is False
