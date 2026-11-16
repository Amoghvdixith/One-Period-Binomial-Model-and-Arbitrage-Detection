"""Exact replication of a two-state contingent claim with stock and cash.

Solve for ``Delta`` (number of shares) and ``B`` (currency amount placed in
the cash account **at time 0**; it grows to ``B * R`` at time 1):

    Delta * Su + B * R = Xu
    Delta * Sd + B * R = Xd

    Delta = (Xu - Xd) / (Su - Sd)
    B     = (u * Xd - d * Xu) / ((u - d) * R)
    cost  = Delta * S0 + B

``Delta``, ``B`` and the cost are computed in exact rational arithmetic and
rounded once to float; the state-by-state verification is then done in
ordinary float arithmetic, and ``numpy.linalg.solve`` provides an
independent float cross-check. ``B < 0`` means borrowing. The replication algebra only needs ``u != d`` and
``R > 0``; it is therefore available even in an arbitrage-containing market,
where its cost is *not* an arbitrage-free valuation.

``Delta`` is the exact payoff-matching coefficient of a static one-period
hedge. It is not, in general, the derivative of the model price with respect
to ``S0`` with ``u`` and ``d`` held fixed (see ``docs/methodology.md``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction

import numpy as np

from .model import MarketParams

__all__ = ["ReplicationResult", "replicate"]


@dataclass(frozen=True)
class ReplicationResult:
    """Replicating portfolio and independent state-by-state verification."""

    claim_name: str
    payoff_up: float
    payoff_down: float
    delta: float
    cash_B: float
    initial_cost: float
    portfolio_up: float
    portfolio_down: float
    error_up: float
    error_down: float
    max_abs_error: float
    linalg_delta: float
    linalg_cash_B: float
    linalg_max_abs_diff: float
    condition_number: float

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


def replicate(params: MarketParams, payoff_up: float, payoff_down: float, claim_name: str = "claim") -> ReplicationResult:
    """Construct and verify the replicating portfolio for payoffs ``(Xu, Xd)``.

    The terminal values of the portfolio are recomputed from ``Delta`` and
    ``B`` (not assumed), giving signed errors ``portfolio - payoff`` in each
    state. A second solution from ``numpy.linalg.solve`` on the 2x2 system is
    reported as an independent cross-check.
    """
    Xu = float(payoff_up)
    Xd = float(payoff_down)
    S0 = float(params.S0)
    R = params.R
    Su = params.Su
    Sd = params.Sd

    # Delta and B are formed in exact rational arithmetic from the (float)
    # payoffs and exact market inputs, then rounded once. This avoids the
    # cancellation in float(u) - float(d) when the states are close together.
    xu_q, xd_q = Fraction(Xu), Fraction(Xd)
    u_q, d_q, R_q, S0_q = params.u_exact, params.d_exact, params.R_exact, params.S0_exact
    delta_q = (xu_q - xd_q) / (S0_q * (u_q - d_q))
    cash_B_q = (u_q * xd_q - d_q * xu_q) / ((u_q - d_q) * R_q)
    delta = float(delta_q)
    cash_B = float(cash_B_q)
    cost = float(delta_q * S0_q + cash_B_q)

    portfolio_up = delta * Su + cash_B * R
    portfolio_down = delta * Sd + cash_B * R
    error_up = portfolio_up - Xu
    error_down = portfolio_down - Xd

    A = np.array([[Su, R], [Sd, R]], dtype=float)
    b = np.array([Xu, Xd], dtype=float)
    lin_delta, lin_B = np.linalg.solve(A, b)
    cond = float(np.linalg.cond(A))

    return ReplicationResult(
        claim_name=claim_name,
        payoff_up=Xu,
        payoff_down=Xd,
        delta=delta,
        cash_B=cash_B,
        initial_cost=cost,
        portfolio_up=portfolio_up,
        portfolio_down=portfolio_down,
        error_up=error_up,
        error_down=error_down,
        max_abs_error=max(abs(error_up), abs(error_down)),
        linalg_delta=float(lin_delta),
        linalg_cash_B=float(lin_B),
        linalg_max_abs_diff=max(abs(float(lin_delta) - delta), abs(float(lin_B) - cash_B)),
        condition_number=cond,
    )
