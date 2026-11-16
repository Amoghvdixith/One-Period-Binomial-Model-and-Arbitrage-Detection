"""Risk-neutral pricing and state-price tests."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from conftest import EXPECTED, approx
from binomial_arbitrage import (
    ClaimSpec,
    MarketParams,
    MarketStatus,
    classify_market,
    replicate,
    risk_neutral_price,
    state_prices,
    terminal_payoffs,
)

ARBITRAGE_FREE_MARKETS = [
    ("100", "1.12", "0.92", "0.02"),
    ("100", "1.05", "0.90", "-0.03"),
    ("100", "1.15", "1.01", "0.05"),
    ("100", "0.99", "0.85", "-0.05"),
    ("37.5", "1.3", "0.7", "0.0"),
    ("250", "1.0201", "1.0199", "0.02"),
]


def _price(params, claim):
    spec = ClaimSpec.from_mapping(claim)
    xu, xd = terminal_payoffs(params.S0, params.u, params.d, spec)
    return risk_neutral_price(params, xu, xd, spec.label())


def test_baseline_exact_targets(baseline_params, baseline_classification):
    assert baseline_params.R == approx(EXPECTED["R"])
    assert baseline_classification.q_candidate == approx(EXPECTED["q"])
    call = _price(baseline_params, {"type": "call", "K": 100})
    put = _price(baseline_params, {"type": "put", "K": 100})
    dig = _price(baseline_params, {"type": "digital", "K": 100, "cash_payout": 1})
    assert (call.payoff_up, call.payoff_down) == (12.0, 0.0)
    assert (put.payoff_up, put.payoff_down) == (0.0, 8.0)
    assert call.arbitrage_free_price == approx(EXPECTED["call_price"])
    assert put.arbitrage_free_price == approx(EXPECTED["put_price"])
    assert dig.arbitrage_free_price == approx(EXPECTED["digital_price"])
    assert call.status is MarketStatus.ARBITRAGE_FREE


def test_guide_stated_price_is_not_reproduced(baseline_params):
    # The guide states a baseline call price of about 8.43; the simple-rate model gives 6/1.02.
    call = _price(baseline_params, {"type": "call", "K": 100})
    assert abs(call.arbitrage_free_price - 8.43) > 2.0


@pytest.mark.parametrize("market", ARBITRAGE_FREE_MARKETS)
@pytest.mark.parametrize(
    "claim",
    [
        {"type": "call", "K": 100},
        {"type": "put", "K": 95},
        {"type": "digital", "K": 100, "cash_payout": 2.5},
        {"type": "generic", "payoff_up": -3, "payoff_down": 7},
    ],
)
def test_risk_neutral_equals_replication_cost(market, claim):
    params = MarketParams.create(*(Decimal(x) for x in market))
    res = _price(params, claim)
    rep = replicate(params, res.payoff_up, res.payoff_down)
    scale = 1.0 + abs(res.payoff_up) + abs(res.payoff_down)
    assert res.arbitrage_free_price == pytest.approx(rep.initial_cost, rel=1e-10, abs=1e-10 * scale)
    assert res.state_price_valuation == pytest.approx(res.arbitrage_free_price, rel=1e-12, abs=1e-12 * scale)


@pytest.mark.parametrize("market", ARBITRAGE_FREE_MARKETS)
def test_state_price_identities(market):
    params = MarketParams.create(*(Decimal(x) for x in market))
    sp = state_prices(params, classify_market(params))
    assert sp is not None
    assert sp.pi_up > 0 and sp.pi_down > 0
    assert sp.pi_up + sp.pi_down == pytest.approx(1.0 / params.R, rel=1e-14)
    assert sp.pi_up * params.Su + sp.pi_down * params.Sd == pytest.approx(float(params.S0), rel=1e-13)


def test_baseline_state_prices_hand_values(baseline_params, baseline_classification):
    sp = state_prices(baseline_params, baseline_classification)
    assert sp.pi_up == approx(Fraction(1, 2) / Fraction(102, 100))
    assert sp.pi_down == approx(Fraction(1, 2) / Fraction(102, 100))


@pytest.mark.parametrize("market", ARBITRAGE_FREE_MARKETS)
@pytest.mark.parametrize("K", ["0", "60", "95", "100", "101.99", "130", "400"])
def test_put_call_parity(market, K):
    params = MarketParams.create(*(Decimal(x) for x in market))
    C = _price(params, {"type": "call", "K": K}).arbitrage_free_price
    P = _price(params, {"type": "put", "K": K}).arbitrage_free_price
    expected = float(params.S0) - float(Decimal(K)) / params.R
    assert C - P == pytest.approx(expected, rel=1e-12, abs=1e-10)


@pytest.mark.parametrize("market", ARBITRAGE_FREE_MARKETS)
@pytest.mark.parametrize("K", ["0", "80", "100", "120", "500"])
def test_call_and_put_bounds(market, K):
    params = MarketParams.create(*(Decimal(x) for x in market))
    S0 = float(params.S0)
    disc_K = float(Decimal(K)) / params.R
    C = _price(params, {"type": "call", "K": K}).arbitrage_free_price
    P = _price(params, {"type": "put", "K": K}).arbitrage_free_price
    eps = 1e-10
    assert max(S0 - disc_K, 0.0) - eps <= C <= S0 + eps
    assert max(disc_K - S0, 0.0) - eps <= P <= disc_K + eps


def test_deep_itm_call_equals_S0_minus_discounted_strike_exactly(baseline_params):
    C = _price(baseline_params, {"type": "call", "K": 80}).arbitrage_free_price
    assert C == approx(Fraction(100) - Fraction(80) / Fraction(102, 100))


def test_zero_strike_call_equals_S0(baseline_params):
    assert _price(baseline_params, {"type": "call", "K": 0}).arbitrage_free_price == approx(100)


def test_high_strike_put_equals_discounted_strike_minus_S0(baseline_params):
    # Corrects the guide: as K grows (both states ITM), P = K/R - S0, not K/R.
    P = _price(baseline_params, {"type": "put", "K": 1000}).arbitrage_free_price
    assert P == approx(Fraction(1000) / Fraction(102, 100) - 100, rel=1e-12, abs_=1e-9)


def test_negative_rate_market_prices():
    params = MarketParams.create(100, Decimal("1.05"), Decimal("0.90"), Decimal("-0.03"))
    cls = classify_market(params)
    assert cls.is_arbitrage_free
    q = (Fraction(97, 100) - Fraction(90, 100)) / Fraction(15, 100)  # = 7/15
    assert cls.q_candidate == approx(q)
    C = _price(params, {"type": "call", "K": 100}).arbitrage_free_price
    assert C == approx(q * 5 / Fraction(97, 100))


@pytest.mark.parametrize(
    "market",
    [
        ("100", "1.25", "1.05", "0.02"),  # R < d
        ("100", "1.05", "0.98", "0.10"),  # R > u
        ("100", "1.12", "1.02", "0.02"),  # R = d
        ("100", "1.12", "0.92", "0.12"),  # R = u
        ("100", "1.12", "1.019999999999", "0.02"),  # unresolved
    ],
)
def test_no_arbitrage_free_price_outside_arbitrage_free_region(market):
    params = MarketParams.create(*(Decimal(x) for x in market))
    res = _price(params, {"type": "call", "K": 100})
    assert res.arbitrage_free_price is None
    assert res.q is None and res.state_prices is None
    assert res.algebraic_replication_cost is not None
    assert "NOT an arbitrage-free" in res.valuation_label
    assert res.status is not MarketStatus.ARBITRAGE_FREE
    assert state_prices(params, classify_market(params)) is None
