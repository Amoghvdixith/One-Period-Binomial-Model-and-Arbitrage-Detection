"""Underlying-market and quote arbitrage tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import EXPECTED
from binomial_arbitrage import MarketParams, MarketStatus, classify_market, quote_arbitrage, underlying_arbitrage


def _market(u, d, r, S0="100"):
    params = MarketParams.create(Decimal(S0), Decimal(u), Decimal(d), Decimal(r))
    return params, classify_market(params)


def test_r_below_d_case_a():
    params, cls = _market("1.25", "1.05", "0.02")
    arb = underlying_arbitrage(params, cls)
    assert arb.case == "A_R_le_d"
    assert (arb.stock_shares, arb.cash_account) == (1.0, -100.0)
    assert arb.initial_cost == 0.0
    assert arb.payoff_up == pytest.approx(100 * (1.25 - 1.02), abs=1e-12)  # 23
    assert arb.payoff_down == pytest.approx(100 * (1.05 - 1.02), abs=1e-12)  # 3
    assert arb.verified


def test_r_above_u_case_b_guide_example():
    params, cls = _market("1.05", "0.98", "0.10")
    arb = underlying_arbitrage(params, cls)
    assert arb.case == "B_R_ge_u"
    assert (arb.stock_shares, arb.cash_account) == (-1.0, 100.0)
    assert arb.payoff_up == pytest.approx(5.0, abs=1e-12)
    assert arb.payoff_down == pytest.approx(12.0, abs=1e-12)
    assert arb.verified


def test_r_equal_d_boundary_arbitrage():
    params, cls = _market("1.12", "1.02", "0.02")
    arb = underlying_arbitrage(params, cls)
    assert cls.status is MarketStatus.ARBITRAGE_R_LE_D
    assert arb.payoff_down == 0.0  # exact zero
    assert arb.payoff_up == pytest.approx(10.0, abs=1e-12)
    assert arb.zero_initial_cost and arb.nonnegative_payoffs and arb.strict_gain_in_some_state
    assert arb.verified


def test_r_equal_u_boundary_arbitrage():
    params, cls = _market("1.12", "0.92", "0.12")
    arb = underlying_arbitrage(params, cls)
    assert cls.status is MarketStatus.ARBITRAGE_R_GE_U
    assert arb.payoff_up == 0.0
    assert arb.payoff_down == pytest.approx(20.0, abs=1e-12)
    assert arb.verified


@pytest.mark.parametrize("market", [("1.25", "1.05", "0.02"), ("1.05", "0.98", "0.10"), ("1.12", "1.02", "0.02"), ("1.12", "0.92", "0.12"), ("0.95", "0.80", "0.30"), ("2.0", "1.5", "-0.6")])
def test_arbitrage_properties_hold_generally(market):
    params, cls = _market(*market)
    arb = underlying_arbitrage(params, cls)
    assert abs(arb.initial_cost) <= 1e-12
    assert min(arb.payoff_up, arb.payoff_down) >= 0.0
    assert max(arb.payoff_up, arb.payoff_down) > 0.0
    assert arb.verified


def test_arbitrage_free_market_has_no_underlying_arbitrage(baseline_params, baseline_classification):
    arb = underlying_arbitrage(baseline_params, baseline_classification)
    assert arb.case is None and not arb.verified


def test_unresolved_inside_boundary_has_no_verified_arbitrage():
    # R exceeds d by 1e-12: mathematically inside (d, u); no stock/cash arbitrage is claimed.
    params, cls = _market("1.12", "1.019999999999", "0.02")
    assert cls.status is MarketStatus.NEAR_BOUNDARY_UNRESOLVED
    arb = underlying_arbitrage(params, cls)
    assert arb.case is None and not arb.verified
    assert arb.market_status == "near_boundary_unresolved"


def test_unresolved_outside_boundary_candidate_checked_exactly():
    # R is below d by 1e-12. The market status stays unresolved, but the
    # candidate portfolio's payoffs are computed exactly: down payoff is
    # +1e-10 (exactly nonnegative) and up payoff is 10 (a strict gain), so the
    # payoff checks do support it.
    params, cls = _market("1.12", "1.020000000001", "0.02")
    assert cls.status is MarketStatus.NEAR_BOUNDARY_UNRESOLVED
    arb = underlying_arbitrage(params, cls)
    assert arb.case == "A_R_le_d"
    assert arb.payoff_down == pytest.approx(1e-10, rel=1e-6)
    assert arb.nonnegative_payoffs and arb.strict_gain_in_some_state
    assert arb.market_status == "near_boundary_unresolved"


def test_tiny_negative_payoff_is_never_called_nonnegative():
    # Exactly constructed: R > u by a tiny amount gives case B with
    # nonnegative payoffs; flip to R < u slightly and there is no candidate.
    params, cls = _market("1.120000000001", "0.92", "0.12")
    arb = underlying_arbitrage(params, cls)
    assert arb.case is None and not arb.verified


def test_unresolved_candidate_can_verify_only_if_payoffs_support_it():
    # With a very loose near-boundary tolerance, a clear arbitrage is "unresolved"
    # yet its payoffs comfortably pass the checks; the status stays unresolved.
    from binomial_arbitrage import Tolerances

    tol = Tolerances(near_boundary_relative_gap=0.5)
    params = MarketParams.create(100, Decimal("1.25"), Decimal("1.05"), Decimal("0.02"), tol)
    cls = classify_market(params, tol)
    assert cls.status is MarketStatus.NEAR_BOUNDARY_UNRESOLVED
    arb = underlying_arbitrage(params, cls, tol)
    assert arb.verified and arb.market_status == "near_boundary_unresolved"


def _check_quote(q, M):
    V = float(EXPECTED["call_price"])
    R = 1.02
    assert q.initial_net_cost == pytest.approx(0.0, abs=1e-10)
    assert q.net_payoff_up == pytest.approx(abs(M - V) * R, abs=1e-10)
    assert q.net_payoff_down == pytest.approx(abs(M - V) * R, abs=1e-10)
    assert q.verified
    assert len(q.legs) == 4


def test_overpriced_quote(baseline_params, baseline_classification):
    q = quote_arbitrage(baseline_params, baseline_classification, 12.0, 0.0, 6.50, "call")
    assert q.direction == "overpriced"
    assert q.legs[0].quantity == -1.0  # short the claim
    assert q.legs[1].quantity == pytest.approx(0.6)  # long Delta shares
    _check_quote(q, 6.50)


def test_underpriced_quote(baseline_params, baseline_classification):
    q = quote_arbitrage(baseline_params, baseline_classification, 12.0, 0.0, 5.20, "call")
    assert q.direction == "underpriced"
    assert q.legs[0].quantity == 1.0  # long the claim
    assert q.legs[1].quantity == pytest.approx(-0.6)  # short Delta shares
    _check_quote(q, 5.20)


def test_quote_legs_sum_state_by_state(baseline_params, baseline_classification):
    q = quote_arbitrage(baseline_params, baseline_classification, 12.0, 0.0, 6.50, "call")
    assert sum(leg.payoff_up for leg in q.legs) == q.net_payoff_up
    assert -sum(leg.time0_cashflow for leg in q.legs) == q.initial_net_cost


def test_exact_quote_agreement(baseline_params, baseline_classification):
    q = quote_arbitrage(baseline_params, baseline_classification, 12.0, 0.0, 5.882352941176471, "call")
    assert q.direction == "within_tolerance"
    assert q.legs == () and not q.verified


def test_quote_not_assessed_in_arbitrage_market():
    params, cls = _market("1.05", "0.98", "0.10")
    q = quote_arbitrage(params, cls, 5.0, 0.0, 1.0, "call")
    assert q.direction == "not_assessed"
    assert "arbitrage_R_ge_u" in q.message
    assert q.replication_cost is None
