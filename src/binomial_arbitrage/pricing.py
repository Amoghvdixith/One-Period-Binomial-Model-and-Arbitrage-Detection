"""Risk-neutral valuation and state prices.

In a strictly arbitrage-free market (``d < R < u``):

    q          = (R - d) / (u - d)            in (0, 1)
    price      = [q * Xu + (1 - q) * Xd] / R
    pi_up      = q / R          (state price: time-0 value of 1 paid in the up state)
    pi_down    = (1 - q) / R
    pi_up + pi_down = 1 / R
    pi_up * Su + pi_down * Sd = S0
    price      = pi_up * Xu + pi_down * Xd

State prices are prices, not probabilities: they sum to ``1/R``, not 1.

Outside the arbitrage-free region no number is returned as an
"arbitrage-free price". The algebraic replication cost is reported in a
separately named field and labelled as not being an arbitrage-free valuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .model import MarketClassification, MarketParams, MarketStatus, classify_market
from .replication import replicate
from .validation import DEFAULT_TOLERANCES, Tolerances

__all__ = ["StatePrices", "PricingResult", "state_prices", "risk_neutral_price"]

NOT_ARBITRAGE_FREE_LABEL = "algebraic replication cost - NOT an arbitrage-free market valuation"


@dataclass(frozen=True)
class StatePrices:
    """Arrow-Debreu state prices with identity residuals (floats)."""

    pi_up: float
    pi_down: float
    sum_minus_inverse_R: float
    stock_reprice_error: float

    def to_dict(self) -> dict[str, float]:
        return {
            "pi_up": self.pi_up,
            "pi_down": self.pi_down,
            "pi_up_plus_pi_down_minus_1_over_R": self.sum_minus_inverse_R,
            "pi_up_Su_plus_pi_down_Sd_minus_S0": self.stock_reprice_error,
        }


@dataclass(frozen=True)
class PricingResult:
    """Valuation outcome for one claim in one market."""

    claim_name: str
    payoff_up: float
    payoff_down: float
    status: MarketStatus
    arbitrage_free_price: float | None
    q: float | None
    state_prices: StatePrices | None
    state_price_valuation: float | None
    algebraic_replication_cost: float | None
    valuation_label: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_name": self.claim_name,
            "payoff_up": self.payoff_up,
            "payoff_down": self.payoff_down,
            "market_status": self.status.value,
            "arbitrage_free_price": self.arbitrage_free_price,
            "risk_neutral_q": self.q,
            "state_prices": self.state_prices.to_dict() if self.state_prices else None,
            "state_price_valuation": self.state_price_valuation,
            "algebraic_replication_cost": self.algebraic_replication_cost,
            "valuation_label": self.valuation_label,
            "message": self.message,
        }


def state_prices(params: MarketParams, classification: MarketClassification) -> StatePrices | None:
    """Return state prices, or ``None`` unless the market is arbitrage-free."""
    if not classification.is_arbitrage_free:
        return None
    R = params.R_exact
    q = (R - params.d_exact) / (params.u_exact - params.d_exact)
    pi_u = q / R
    pi_d = (1 - q) / R
    pu, pd = float(pi_u), float(pi_d)
    return StatePrices(
        pi_up=pu,
        pi_down=pd,
        sum_minus_inverse_R=(pu + pd) - 1.0 / params.R,
        stock_reprice_error=pu * params.Su + pd * params.Sd - float(params.S0),
    )


def risk_neutral_price(
    params: MarketParams,
    payoff_up: float,
    payoff_down: float,
    claim_name: str = "claim",
    classification: MarketClassification | None = None,
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> PricingResult:
    """Price a claim by risk-neutral expectation when (and only when) permitted."""
    if classification is None:
        classification = classify_market(params, tolerances)
    Xu, Xd = float(payoff_up), float(payoff_down)

    if classification.is_arbitrage_free:
        q_exact = (params.R_exact - params.d_exact) / (params.u_exact - params.d_exact)
        q = float(q_exact)
        one_minus_q = float(Fraction(1) - q_exact)
        price = (q * Xu + one_minus_q * Xd) / params.R
        sp = state_prices(params, classification)
        assert sp is not None
        return PricingResult(
            claim_name=claim_name,
            payoff_up=Xu,
            payoff_down=Xd,
            status=classification.status,
            arbitrage_free_price=price,
            q=q,
            state_prices=sp,
            state_price_valuation=sp.pi_up * Xu + sp.pi_down * Xd,
            algebraic_replication_cost=None,
            valuation_label="arbitrage-free price (risk-neutral expectation discounted by R = 1 + r)",
            message=classification.message,
        )

    cost = replicate(params, Xu, Xd, claim_name).initial_cost
    return PricingResult(
        claim_name=claim_name,
        payoff_up=Xu,
        payoff_down=Xd,
        status=classification.status,
        arbitrage_free_price=None,
        q=None,
        state_prices=None,
        state_price_valuation=None,
        algebraic_replication_cost=cost,
        valuation_label=NOT_ARBITRAGE_FREE_LABEL,
        message=(
            f"No arbitrage-free price: market status is '{classification.status.value}'. "
            + classification.message
        ),
    )
