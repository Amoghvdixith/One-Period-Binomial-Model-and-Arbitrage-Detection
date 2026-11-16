"""binomial_arbitrage: an educational one-period, two-state binomial model.

Convention: ``r`` is the effective simple risk-free return over the single
model period and ``R = 1 + r``. See ``docs/methodology.md``.
"""

from .arbitrage import QuoteArbitrage, UnderlyingArbitrage, quote_arbitrage, underlying_arbitrage
from .model import (
    RATE_CONVENTION,
    MarketClassification,
    MarketParams,
    MarketStatus,
    classify_inputs,
    classify_market,
)
from .payoffs import ClaimSpec, call_payoff, digital_call_payoff, put_payoff, terminal_payoffs
from .pricing import PricingResult, StatePrices, risk_neutral_price, state_prices
from .replication import ReplicationResult, replicate
from .validation import DEFAULT_TOLERANCES, Tolerances, ValidationError

__version__ = "0.1.0"

__all__ = [
    "RATE_CONVENTION",
    "DEFAULT_TOLERANCES",
    "Tolerances",
    "ValidationError",
    "MarketParams",
    "MarketStatus",
    "MarketClassification",
    "classify_market",
    "classify_inputs",
    "ClaimSpec",
    "call_payoff",
    "put_payoff",
    "digital_call_payoff",
    "terminal_payoffs",
    "risk_neutral_price",
    "state_prices",
    "PricingResult",
    "StatePrices",
    "replicate",
    "ReplicationResult",
    "underlying_arbitrage",
    "quote_arbitrage",
    "UnderlyingArbitrage",
    "QuoteArbitrage",
    "__version__",
]
