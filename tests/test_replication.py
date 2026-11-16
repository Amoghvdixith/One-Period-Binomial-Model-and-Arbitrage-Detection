"""Replication tests: hand-calculated holdings and independent checks."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from conftest import EXPECTED, approx
from binomial_arbitrage import MarketParams, replicate


def test_call_hand_calculated_holdings(baseline_params):
    rep = replicate(baseline_params, 12.0, 0.0, "call")
    assert rep.delta == approx(EXPECTED["call_delta"])
    assert rep.cash_B == approx(EXPECTED["call_B"])
    assert rep.initial_cost == approx(EXPECTED["call_price"])
    assert rep.cash_B < 0  # borrowing


def test_put_specific_replication(baseline_params):
    rep = replicate(baseline_params, 0.0, 8.0, "put")
    assert rep.delta == approx(EXPECTED["put_delta"])
    assert rep.cash_B == approx(EXPECTED["put_B"])
    assert rep.initial_cost == approx(EXPECTED["put_price"])
    assert rep.delta < 0 and rep.cash_B > 0  # short stock, lend cash
    # Put checks are computed from the put's own payoffs, not reused from the call.
    call = replicate(baseline_params, 12.0, 0.0, "call")
    assert (rep.payoff_up, rep.payoff_down) != (call.payoff_up, call.payoff_down)
    assert rep.portfolio_down == pytest.approx(8.0, abs=1e-12)


def test_both_states_match_independently(baseline_params):
    rep = replicate(baseline_params, 12.0, 0.0)
    # Recompute terminal values by hand from Delta and B.
    up = rep.delta * 112.0 + rep.cash_B * 1.02
    down = rep.delta * 92.0 + rep.cash_B * 1.02
    assert up == pytest.approx(12.0, abs=1e-11)
    assert down == pytest.approx(0.0, abs=1e-11)
    assert rep.error_up == pytest.approx(up - 12.0, abs=1e-15)
    assert rep.max_abs_error <= 1e-11


@pytest.mark.parametrize(
    "market,payoffs",
    [
        (("100", "1.12", "0.92", "0.02"), (-5.0, 10.0)),
        (("100", "1.12", "0.92", "0.02"), (7.0, 7.0)),
        (("50", "1.3", "0.6", "0.1"), (0.0, -20.0)),
        (("100", "0.99", "0.85", "-0.05"), (3.0, 0.0)),
        (("100", "1.25", "1.05", "0.02"), (25.0, 5.0)),  # arbitrage market: algebra still works
    ],
)
def test_generic_claims_replicated(market, payoffs):
    params = MarketParams.create(*(Decimal(x) for x in market))
    rep = replicate(params, *payoffs)
    assert rep.max_abs_error <= 1e-10 * (1 + max(abs(p) for p in payoffs))


def test_constant_payoff_is_pure_cash(baseline_params):
    rep = replicate(baseline_params, 7.0, 7.0)
    assert rep.delta == 0.0
    assert rep.cash_B == approx(Fraction(7) / Fraction(102, 100))


def test_exact_rational_cross_check():
    # Exact Fraction solution of the 2x2 system for an awkward market.
    S0, u, d, r = Fraction(733, 10), Fraction(113, 100), Fraction(87, 100), Fraction(17, 1000)
    Xu, Xd = Fraction(-31, 7), Fraction(19, 3)
    R = 1 + r
    delta = (Xu - Xd) / (S0 * u - S0 * d)
    B = (u * Xd - d * Xu) / ((u - d) * R)
    params = MarketParams.create(Decimal("73.3"), Decimal("1.13"), Decimal("0.87"), Decimal("0.017"))
    rep = replicate(params, float(Xu), float(Xd))
    assert rep.delta == approx(delta, rel=1e-13, abs_=1e-13)
    assert rep.cash_B == approx(B, rel=1e-13, abs_=1e-12)


def test_independent_linear_system_cross_check(baseline_params):
    rep = replicate(baseline_params, 12.0, 0.0)
    A = np.array([[112.0, 1.02], [92.0, 1.02]])
    sol = np.linalg.solve(A, np.array([12.0, 0.0]))
    assert rep.linalg_delta == pytest.approx(sol[0], abs=1e-12)
    assert rep.linalg_cash_B == pytest.approx(sol[1], abs=1e-10)
    assert rep.linalg_max_abs_diff <= 1e-10
    assert np.isfinite(rep.condition_number)
