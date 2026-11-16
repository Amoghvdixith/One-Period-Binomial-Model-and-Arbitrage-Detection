"""One-period, two-state market model and no-arbitrage classification.

Interest-rate convention (used everywhere in this package):

    r = effective simple risk-free return over the single model period
    R = 1 + r          (cash B at time 0 grows to B * R at time 1)

There is no annualisation, no maturity parameter and no ``exp(r)``. A user
starting from a continuously compounded annual rate ``rc`` and maturity ``T``
must convert explicitly: ``R = exp(rc * T)``, ``r = R - 1``.

The labels "up" and "down" only mean ``Su > Sd``; both states may be gains or
both may be losses relative to ``S0``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Any

from .validation import (
    DEFAULT_TOLERANCES,
    Tolerances,
    ValidationError,
    to_fraction,
    validate_market_inputs,
)

__all__ = [
    "MarketStatus",
    "MarketParams",
    "MarketClassification",
    "classify_market",
    "classify_inputs",
]

RATE_CONVENTION = (
    "r is the effective simple risk-free return over one model period; R = 1 + r; "
    "cash B at time 0 grows to B*R; no annualisation; no exp(r)."
)


class MarketStatus(str, Enum):
    """Possible classifications of a one-period stock/cash market."""

    ARBITRAGE_FREE = "arbitrage_free"
    ARBITRAGE_R_LE_D = "arbitrage_R_le_d"
    ARBITRAGE_R_GE_U = "arbitrage_R_ge_u"
    NEAR_BOUNDARY_UNRESOLVED = "near_boundary_unresolved"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class MarketParams:
    """Validated market inputs held as exact Decimals.

    Create instances with :meth:`MarketParams.create`, which validates inputs.
    """

    S0: Decimal
    u: Decimal
    d: Decimal
    r: Decimal
    warnings: tuple[str, ...] = field(default=())

    @classmethod
    def create(
        cls,
        S0: Any,
        u: Any,
        d: Any,
        r: Any,
        tolerances: Tolerances = DEFAULT_TOLERANCES,
    ) -> "MarketParams":
        """Validate inputs and build a :class:`MarketParams`.

        Raises:
            ValidationError: If the inputs are mathematically invalid.
        """
        S0_d, u_d, d_d, r_d, warnings = validate_market_inputs(S0, u, d, r, tolerances)
        return cls(S0=S0_d, u=u_d, d=d_d, r=r_d, warnings=tuple(warnings))

    # Exact rational views -------------------------------------------------
    @property
    def R_exact(self) -> Fraction:
        """Exact gross one-period risk-free growth ``R = 1 + r``."""
        return 1 + to_fraction(self.r)

    @property
    def u_exact(self) -> Fraction:
        return to_fraction(self.u)

    @property
    def d_exact(self) -> Fraction:
        return to_fraction(self.d)

    @property
    def S0_exact(self) -> Fraction:
        return to_fraction(self.S0)

    # Float views used for numerical work ----------------------------------
    @property
    def R(self) -> float:
        """Gross risk-free growth ``1 + r`` as a float."""
        return float(self.R_exact)

    @property
    def Su(self) -> float:
        """Up-state terminal stock price ``S0 * u``."""
        return float(self.S0_exact * self.u_exact)

    @property
    def Sd(self) -> float:
        """Down-state terminal stock price ``S0 * d``."""
        return float(self.S0_exact * self.d_exact)

    def as_floats(self) -> dict[str, float]:
        """Inputs and derived quantities as floats (for tables and JSON)."""
        return {
            "S0": float(self.S0),
            "u": float(self.u),
            "d": float(self.d),
            "r": float(self.r),
            "R": self.R,
            "Su": self.Su,
            "Sd": self.Sd,
        }


@dataclass(frozen=True)
class MarketClassification:
    """Result of the no-arbitrage classification.

    Attributes:
        status: One of :class:`MarketStatus`.
        q_candidate: ``(R - d)/(u - d)`` as a float, never clipped. It is a
            risk-neutral probability only when ``status`` is arbitrage-free.
        gap_lower: Exact ``R - d`` as float.
        gap_upper: Exact ``u - R`` as float.
        relative_gap: ``min(|R - d|, |u - R|) / (u - d)`` (dimensionless).
        exact_boundary: ``"R_equals_d"``, ``"R_equals_u"`` or ``None``.
        message: Human-readable explanation.
        warnings: Conditioning and boundary warnings.
    """

    status: MarketStatus
    q_candidate: float | None
    gap_lower: float | None
    gap_upper: float | None
    relative_gap: float | None
    exact_boundary: str | None
    message: str
    warnings: tuple[str, ...] = ()

    @property
    def is_arbitrage_free(self) -> bool:
        return self.status is MarketStatus.ARBITRAGE_FREE

    @property
    def contains_arbitrage(self) -> bool:
        return self.status in (MarketStatus.ARBITRAGE_R_LE_D, MarketStatus.ARBITRAGE_R_GE_U)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "q_candidate": self.q_candidate,
            "q_is_valid_risk_neutral_probability": self.is_arbitrage_free,
            "gap_R_minus_d": self.gap_lower,
            "gap_u_minus_R": self.gap_upper,
            "relative_gap": self.relative_gap,
            "exact_boundary": self.exact_boundary,
            "message": self.message,
            "warnings": list(self.warnings),
        }


def classify_market(
    params: MarketParams, tolerances: Tolerances = DEFAULT_TOLERANCES
) -> MarketClassification:
    """Classify a validated market using exact rational arithmetic.

    Strict no-arbitrage requires ``d < R < u``. Both equality cases contain
    arbitrage because both terminal states are assumed possible. A market
    whose relative distance to a boundary is positive but below
    ``tolerances.near_boundary_relative_gap`` is reported as
    ``near_boundary_unresolved`` (on either side of the boundary), because a
    confident classification would rest on digits beyond any realistic input
    precision.
    """
    R = params.R_exact
    u = params.u_exact
    d = params.d_exact
    spread = u - d
    gap_lower = R - d
    gap_upper = u - R
    q = gap_lower / spread
    rel_gap = min(abs(gap_lower), abs(gap_upper)) / spread
    warnings = list(params.warnings)
    tol = Fraction(tolerances.near_boundary_relative_gap)

    common = dict(
        q_candidate=float(q),
        gap_lower=float(gap_lower),
        gap_upper=float(gap_upper),
        relative_gap=float(rel_gap),
    )

    if gap_lower == 0:
        return MarketClassification(
            status=MarketStatus.ARBITRAGE_R_LE_D,
            exact_boundary="R_equals_d",
            message="R equals d exactly: the stock weakly dominates cash (down-state gain zero, up-state gain positive).",
            warnings=tuple(warnings),
            **common,
        )
    if gap_upper == 0:
        return MarketClassification(
            status=MarketStatus.ARBITRAGE_R_GE_U,
            exact_boundary="R_equals_u",
            message="R equals u exactly: cash weakly dominates the stock (up-state gain zero, down-state gain positive).",
            warnings=tuple(warnings),
            **common,
        )
    if rel_gap < tol:
        side = "inside" if (gap_lower > 0 and gap_upper > 0) else "outside"
        warnings.append(
            f"near_boundary: relative gap {float(rel_gap):.3e} < tolerance {tolerances.near_boundary_relative_gap:.1e} "
            f"(R is mathematically {side} the open interval (d, u))"
        )
        return MarketClassification(
            status=MarketStatus.NEAR_BOUNDARY_UNRESOLVED,
            exact_boundary=None,
            message=(
                "R is within the numerical tolerance of a boundary; the classification is reported as unresolved "
                "and no arbitrage-free price or verified arbitrage is claimed."
            ),
            warnings=tuple(warnings),
            **common,
        )
    if gap_lower < 0:
        return MarketClassification(
            status=MarketStatus.ARBITRAGE_R_LE_D,
            exact_boundary=None,
            message="R < d: the stock strictly dominates cash in both states.",
            warnings=tuple(warnings),
            **common,
        )
    if gap_upper < 0:
        return MarketClassification(
            status=MarketStatus.ARBITRAGE_R_GE_U,
            exact_boundary=None,
            message="R > u: cash strictly dominates the stock in both states.",
            warnings=tuple(warnings),
            **common,
        )
    return MarketClassification(
        status=MarketStatus.ARBITRAGE_FREE,
        exact_boundary=None,
        message="d < R < u strictly: the market is arbitrage-free and q is a valid risk-neutral probability in (0, 1).",
        warnings=tuple(warnings),
        **common,
    )


def classify_inputs(
    S0: Any, u: Any, d: Any, r: Any, tolerances: Tolerances = DEFAULT_TOLERANCES
) -> tuple[MarketParams | None, MarketClassification]:
    """Validate and classify raw inputs without raising.

    Returns ``(None, classification)`` with status ``invalid_input`` when
    validation fails, so callers can tabulate rejected scenarios.
    """
    try:
        params = MarketParams.create(S0, u, d, r, tolerances)
    except ValidationError as exc:
        return None, MarketClassification(
            status=MarketStatus.INVALID_INPUT,
            q_candidate=None,
            gap_lower=None,
            gap_upper=None,
            relative_gap=None,
            exact_boundary=None,
            message=str(exc),
        )
    return params, classify_market(params, tolerances)
