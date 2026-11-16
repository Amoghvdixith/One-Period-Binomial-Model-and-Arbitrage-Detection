"""Terminal payoff functions (independent of pricing and file writing).

All functions accept scalars or NumPy arrays of terminal stock prices.

* European call: ``max(S_T - K, 0)``
* European put: ``max(K - S_T, 0)``
* Cash-or-nothing digital call: ``payout * 1{S_T > K}``. The inequality is
  **strict**: a terminal price exactly equal to the strike pays nothing.
* Generic claim: any finite pair ``(Xu, Xd)``; negative payoffs are allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any

import numpy as np

from .validation import (
    ValidationError,
    to_fraction,
    validate_cash_payout,
    validate_payoffs,
    validate_strike,
)

__all__ = [
    "call_payoff",
    "put_payoff",
    "digital_call_payoff",
    "ClaimSpec",
    "terminal_payoffs",
]

CLAIM_TYPES = ("call", "put", "digital", "generic")


def call_payoff(S_T: Any, K: float) -> Any:
    """European call payoff ``max(S_T - K, 0)``."""
    return np.maximum(np.asarray(S_T, dtype=float) - float(K), 0.0)[()]


def put_payoff(S_T: Any, K: float) -> Any:
    """European put payoff ``max(K - S_T, 0)``."""
    return np.maximum(float(K) - np.asarray(S_T, dtype=float), 0.0)[()]


def digital_call_payoff(S_T: Any, K: float, cash_payout: float = 1.0) -> Any:
    """Cash-or-nothing digital call ``payout * 1{S_T > K}`` (strict inequality)."""
    return np.where(np.asarray(S_T, dtype=float) > float(K), float(cash_payout), 0.0)[()]


@dataclass(frozen=True)
class ClaimSpec:
    """Specification of a contingent claim.

    Attributes:
        claim_type: ``"call"``, ``"put"``, ``"digital"`` or ``"generic"``.
        K: Strike (Decimal) for strike-based claims.
        cash_payout: Digital payout (Decimal).
        payoff_up / payoff_down: Generic terminal payoffs.
    """

    claim_type: str
    K: Decimal | None = None
    cash_payout: Decimal | None = None
    payoff_up: float | None = None
    payoff_down: float | None = None

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "ClaimSpec":
        """Build and validate a claim from a configuration mapping."""
        claim_type = str(mapping.get("type", "")).lower()
        if claim_type not in CLAIM_TYPES:
            raise ValidationError(f"claim type must be one of {CLAIM_TYPES}, got {mapping.get('type')!r}")
        if claim_type in ("call", "put"):
            return cls(claim_type, K=validate_strike(mapping.get("K")))
        if claim_type == "digital":
            return cls(
                claim_type,
                K=validate_strike(mapping.get("K")),
                cash_payout=validate_cash_payout(mapping.get("cash_payout", 1)),
            )
        xu, xd = validate_payoffs(mapping.get("payoff_up"), mapping.get("payoff_down"))
        return cls(claim_type, payoff_up=xu, payoff_down=xd)

    def label(self) -> str:
        if self.claim_type == "generic":
            return f"generic(Xu={self.payoff_up:g}, Xd={self.payoff_down:g})"
        if self.claim_type == "digital":
            return f"digital(K={self.K}, payout={self.cash_payout})"
        return f"{self.claim_type}(K={self.K})"


def _exact_payoff(S_T: Fraction, spec: ClaimSpec) -> Fraction:
    K = to_fraction(spec.K) if spec.K is not None else None
    if spec.claim_type == "call":
        return max(S_T - K, Fraction(0))
    if spec.claim_type == "put":
        return max(K - S_T, Fraction(0))
    if spec.claim_type == "digital":
        return to_fraction(spec.cash_payout) if S_T > K else Fraction(0)
    raise ValidationError(f"exact payoff not defined for {spec.claim_type}")


def terminal_payoffs(S0: Decimal, u: Decimal, d: Decimal, spec: ClaimSpec) -> tuple[float, float]:
    """Return ``(Xu, Xd)`` for a claim given exact market inputs.

    Terminal prices ``Su = S0*u`` and ``Sd = S0*d`` are formed exactly, so a
    strike equal to a terminal price is detected exactly (e.g. the digital's
    strict inequality and at-the-money call/put payoffs of exactly zero).
    """
    if spec.claim_type == "generic":
        return float(spec.payoff_up), float(spec.payoff_down)
    Su = to_fraction(S0) * to_fraction(u)
    Sd = to_fraction(S0) * to_fraction(d)
    return float(_exact_payoff(Su, spec)), float(_exact_payoff(Sd, spec))
