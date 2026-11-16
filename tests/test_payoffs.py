"""Payoff function tests (independent of pricing)."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from binomial_arbitrage.payoffs import ClaimSpec, call_payoff, digital_call_payoff, put_payoff, terminal_payoffs


def test_call_in_and_out_of_the_money():
    assert call_payoff(112.0, 100.0) == 12.0
    assert call_payoff(92.0, 100.0) == 0.0


def test_put_in_and_out_of_the_money():
    assert put_payoff(92.0, 100.0) == 8.0
    assert put_payoff(112.0, 100.0) == 0.0


def test_strike_equality_pays_zero_for_call_put_and_digital():
    assert call_payoff(100.0, 100.0) == 0.0
    assert put_payoff(100.0, 100.0) == 0.0
    assert digital_call_payoff(100.0, 100.0, 5.0) == 0.0  # strict inequality


def test_digital_strict_inequality_just_above_strike():
    assert digital_call_payoff(np.nextafter(100.0, 200.0), 100.0, 2.5) == 2.5


def test_zero_strike():
    assert call_payoff(112.0, 0.0) == 112.0
    assert put_payoff(92.0, 0.0) == 0.0
    assert digital_call_payoff(92.0, 0.0) == 1.0


def test_vectorised_payoffs():
    S = np.array([80.0, 100.0, 120.0])
    np.testing.assert_array_equal(call_payoff(S, 100.0), [0.0, 0.0, 20.0])
    np.testing.assert_array_equal(put_payoff(S, 100.0), [20.0, 0.0, 0.0])
    np.testing.assert_array_equal(digital_call_payoff(S, 100.0, 1.0), [0.0, 0.0, 1.0])


def test_terminal_payoffs_baseline():
    S0, u, d = Decimal(100), Decimal("1.12"), Decimal("0.92")
    assert terminal_payoffs(S0, u, d, ClaimSpec.from_mapping({"type": "call", "K": 100})) == (12.0, 0.0)
    assert terminal_payoffs(S0, u, d, ClaimSpec.from_mapping({"type": "put", "K": 100})) == (0.0, 8.0)
    assert terminal_payoffs(S0, u, d, ClaimSpec.from_mapping({"type": "digital", "K": 100})) == (1.0, 0.0)


def test_terminal_payoffs_exact_strike_hit():
    # Su = 100 * 1.12 = 112 exactly; K = 112 must give zero call payoff and no digital payout.
    S0, u, d = Decimal(100), Decimal("1.12"), Decimal("0.92")
    assert terminal_payoffs(S0, u, d, ClaimSpec.from_mapping({"type": "call", "K": 112})) == (0.0, 0.0)
    assert terminal_payoffs(S0, u, d, ClaimSpec.from_mapping({"type": "digital", "K": 112, "cash_payout": 3})) == (0.0, 0.0)


def test_generic_payoffs_may_be_negative():
    spec = ClaimSpec.from_mapping({"type": "generic", "payoff_up": -5, "payoff_down": 10})
    assert terminal_payoffs(Decimal(100), Decimal("1.12"), Decimal("0.92"), spec) == (-5.0, 10.0)


def test_generic_payoffs_must_be_finite():
    from binomial_arbitrage import ValidationError

    with pytest.raises(ValidationError):
        ClaimSpec.from_mapping({"type": "generic", "payoff_up": float("nan"), "payoff_down": 1})
