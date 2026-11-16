"""Explicit arbitrage portfolios.

Underlying (stock/cash) arbitrage
---------------------------------
Case A, ``R <= d``: buy 1 share and borrow ``S0`` in the cash account.
    cost 0; payoffs ``S0*(u - R)`` (up) and ``S0*(d - R)`` (down), both >= 0,
    and the up payoff is strictly positive because ``u > d >= R``.
Case B, ``R >= u``: short 1 share and deposit ``S0``.
    cost 0; payoffs ``S0*(R - u)`` (up) and ``S0*(R - d)`` (down), both >= 0,
    and the down payoff is strictly positive because ``R >= u > d``.

Payoffs are computed in exact rational arithmetic and then converted to
float, so the equality cases produce an exact zero in one state.

Quote arbitrage
---------------
Only assessed when the stock/cash market is strictly arbitrage-free. With a
quoted claim price ``M`` and replication cost ``V``:

* ``M > V``: short the claim, buy the replicating portfolio, invest ``M - V``.
* ``M < V``: buy the claim, short the replicating portfolio, invest ``V - M``.

Either way the initial net cost is 0 and the terminal profit is
``|M - V| * R`` in both states. All legs are listed and checked state by
state. This is a frictionless model result, not evidence that a real quote is
executable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import MarketClassification, MarketParams, MarketStatus
from .replication import replicate
from .validation import DEFAULT_TOLERANCES, Tolerances

__all__ = ["UnderlyingArbitrage", "QuoteLeg", "QuoteArbitrage", "underlying_arbitrage", "quote_arbitrage"]


@dataclass(frozen=True)
class UnderlyingArbitrage:
    """Stock/cash arbitrage portfolio and its verification.

    ``cash_account`` is the signed time-0 cash position (negative = borrowing).
    ``initial_cost`` is the time-0 outlay ``stock_shares*S0 + cash_account``.
    """

    market_status: str
    case: str | None
    stock_shares: float
    cash_account: float
    initial_cost: float
    payoff_up: float
    payoff_down: float
    zero_initial_cost: bool
    nonnegative_payoffs: bool
    strict_gain_in_some_state: bool
    verified: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class QuoteLeg:
    """One leg of a quote-arbitrage portfolio.

    ``time0_cashflow`` is cash received at time 0 (negative = paid).
    """

    leg: str
    quantity: float
    time0_cashflow: float
    payoff_up: float
    payoff_down: float


@dataclass(frozen=True)
class QuoteArbitrage:
    """Quote-versus-replication comparison and (if any) the arbitrage legs."""

    claim_name: str
    market_status: str
    quoted_price: float
    replication_cost: float | None
    difference: float | None
    tolerance: float | None
    direction: str
    legs: tuple[QuoteLeg, ...] = field(default=())
    initial_net_cost: float | None = None
    net_payoff_up: float | None = None
    net_payoff_down: float | None = None
    expected_profit: float | None = None
    verified: bool = False
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in self.__dict__.items() if k != "legs"}
        out["legs"] = [leg.__dict__ for leg in self.legs]
        return out


def underlying_arbitrage(
    params: MarketParams,
    classification: MarketClassification,
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> UnderlyingArbitrage:
    """Build and verify the stock/cash arbitrage portfolio, if one exists.

    For arbitrage-free markets the result has ``case=None`` and is not
    verified (there is nothing to verify). For near-boundary markets the
    candidate on the mathematically indicated side is constructed, but it is
    only marked verified if the tolerance-based payoff checks pass, and the
    market status remains ``near_boundary_unresolved``.
    """
    status = classification.status
    R = params.R_exact
    S0 = params.S0_exact
    u = params.u_exact
    d = params.d_exact

    if R <= d:
        case = "A_R_le_d"
        shares, cash = 1.0, -float(S0)
        pay_u, pay_d = S0 * (u - R), S0 * (d - R)
        desc = "buy 1 share, borrow S0 in the cash account"
    elif R >= u:
        case = "B_R_ge_u"
        shares, cash = -1.0, float(S0)
        pay_u, pay_d = S0 * (R - u), S0 * (R - d)
        desc = "short 1 share, deposit S0 in the cash account"
    else:
        msg = (
            "No stock/cash arbitrage: d < R < u."
            if status is MarketStatus.ARBITRAGE_FREE
            else "No stock/cash arbitrage candidate: R lies (narrowly) inside (d, u); status remains unresolved."
        )
        return UnderlyingArbitrage(
            market_status=status.value,
            case=None,
            stock_shares=0.0,
            cash_account=0.0,
            initial_cost=0.0,
            payoff_up=0.0,
            payoff_down=0.0,
            zero_initial_cost=True,
            nonnegative_payoffs=True,
            strict_gain_in_some_state=False,
            verified=False,
            message=msg,
        )

    initial_cost = shares * float(S0) + cash
    pu, pd = float(pay_u), float(pay_d)
    tol = tolerances.payoff_abs_tol
    zero_cost = abs(initial_cost) <= tol
    # Nonnegativity is checked exactly (no tolerance), so a payoff that is
    # negative by even a tiny amount can never be passed as "nonnegative".
    nonneg = pay_u >= 0 and pay_d >= 0
    # A strict gain must exceed the payoff tolerance to count.
    strict = max(pu, pd) > tol
    verified = zero_cost and nonneg and strict
    if status is MarketStatus.NEAR_BOUNDARY_UNRESOLVED:
        msg = (
            f"Candidate portfolio ({desc}) constructed for an unresolved near-boundary market; "
            + ("payoff checks pass." if verified else "payoff checks do NOT establish a verified arbitrage at the stated tolerance.")
        )
    else:
        msg = f"{desc}; " + ("verified: zero cost, nonnegative payoffs, strict gain in at least one state." if verified else "verification FAILED.")
    return UnderlyingArbitrage(
        market_status=status.value,
        case=case,
        stock_shares=shares,
        cash_account=cash,
        initial_cost=initial_cost,
        payoff_up=pu,
        payoff_down=pd,
        zero_initial_cost=zero_cost,
        nonnegative_payoffs=nonneg,
        strict_gain_in_some_state=strict,
        verified=verified,
        message=msg,
    )


def quote_arbitrage(
    params: MarketParams,
    classification: MarketClassification,
    payoff_up: float,
    payoff_down: float,
    quoted_price: float,
    claim_name: str = "claim",
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> QuoteArbitrage:
    """Assess a quoted claim price against its replication cost."""
    M = float(quoted_price)
    if not classification.is_arbitrage_free:
        return QuoteArbitrage(
            claim_name=claim_name,
            market_status=classification.status.value,
            quoted_price=M,
            replication_cost=None,
            difference=None,
            tolerance=None,
            direction="not_assessed",
            message=(
                "Quote not assessed as a standalone derivative arbitrage because the stock/cash market "
                f"is '{classification.status.value}'. Underlying diagnosis: {classification.message}"
            ),
        )

    rep = replicate(params, payoff_up, payoff_down, claim_name)
    V = rep.initial_cost
    S0 = float(params.S0)
    R = params.R
    Su, Sd = params.Su, params.Sd
    diff = M - V
    tol = tolerances.quote_abs_tol + tolerances.quote_rel_tol * max(abs(M), abs(V))

    if abs(diff) <= tol:
        return QuoteArbitrage(
            claim_name=claim_name,
            market_status=classification.status.value,
            quoted_price=M,
            replication_cost=V,
            difference=diff,
            tolerance=tol,
            direction="within_tolerance",
            message=f"No discrepancy detected at the specified tolerance ({tol:.3e} currency units).",
        )

    sign = 1.0 if diff > 0 else -1.0  # +1: claim overpriced (short claim, long replica)
    surplus = abs(diff)
    legs = (
        QuoteLeg(
            leg="short claim" if sign > 0 else "long claim",
            quantity=-sign,
            time0_cashflow=sign * M,
            payoff_up=-sign * rep.payoff_up,
            payoff_down=-sign * rep.payoff_down,
        ),
        QuoteLeg(
            leg="stock (replicating Delta)" if sign > 0 else "stock (short replicating Delta)",
            quantity=sign * rep.delta,
            time0_cashflow=-sign * rep.delta * S0,
            payoff_up=sign * rep.delta * Su,
            payoff_down=sign * rep.delta * Sd,
        ),
        QuoteLeg(
            leg="cash account (replicating B)" if sign > 0 else "cash account (short replicating B)",
            quantity=sign * rep.cash_B,
            time0_cashflow=-sign * rep.cash_B,
            payoff_up=sign * rep.cash_B * R,
            payoff_down=sign * rep.cash_B * R,
        ),
        QuoteLeg(
            leg="invest surplus abs(M - V) in cash account",
            quantity=surplus,
            time0_cashflow=-surplus,
            payoff_up=surplus * R,
            payoff_down=surplus * R,
        ),
    )
    # Normalise IEEE negative zeros (e.g. -1 * 0.0) so tables show 0, not -0.
    legs = tuple(
        QuoteLeg(lg.leg, lg.quantity + 0.0, lg.time0_cashflow + 0.0, lg.payoff_up + 0.0, lg.payoff_down + 0.0)
        for lg in legs
    )
    initial_net_cost = -sum(leg.time0_cashflow for leg in legs) + 0.0
    net_up = sum(leg.payoff_up for leg in legs)
    net_down = sum(leg.payoff_down for leg in legs)
    expected = surplus * R
    check_tol = tolerances.payoff_abs_tol * (1.0 + max(abs(M), abs(V), abs(S0)))
    verified = (
        abs(initial_net_cost) <= check_tol
        and abs(net_up - expected) <= check_tol
        and abs(net_down - expected) <= check_tol
        and net_up > 0
        and net_down > 0
    )
    direction = "overpriced" if sign > 0 else "underpriced"
    return QuoteArbitrage(
        claim_name=claim_name,
        market_status=classification.status.value,
        quoted_price=M,
        replication_cost=V,
        difference=diff,
        tolerance=tol,
        direction=direction,
        legs=legs,
        initial_net_cost=initial_net_cost,
        net_payoff_up=net_up,
        net_payoff_down=net_down,
        expected_profit=expected,
        verified=verified,
        message=(
            f"Quote {direction} by {surplus:.10g}; locked-in profit |M - V| * R = {expected:.10g} in both states "
            "(frictionless model; not evidence that a real quote is executable)."
        ),
    )
