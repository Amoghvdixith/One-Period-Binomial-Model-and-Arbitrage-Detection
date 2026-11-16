"""Input validation, exact-number conversion and numerical tolerance policy.

Three kinds of outcome are kept separate throughout the package:

* **Invalid mathematical input** (non-finite numbers, ``S0 <= 0``, ``u <= d``,
  ``d <= 0``, ``r <= -1``, negative strike or payout, or a state separation so
  narrow that the replication system is ill-conditioned). These raise
  :class:`ValidationError` and no model is built.
* **A validly specified market that contains arbitrage** (``R <= d`` or
  ``R >= u``). This is *not* a validation failure; it is diagnosed by
  :func:`binomial_arbitrage.model.classify_market`.
* **A numerically unresolved near-boundary market**, also diagnosed by the
  classifier using the tolerance in :class:`Tolerances`.

Exact arithmetic
----------------
Inputs are converted to :class:`decimal.Decimal`. JSON configuration files are
read with ``parse_float=Decimal`` so that a literal such as ``1.02`` is held
exactly. Python floats are converted through their shortest round-trip
representation (``Decimal(repr(x))``), i.e. ``0.02`` is interpreted as the
decimal 0.02 that the user typed, not as the nearest binary double. All
boundary comparisons are then made in exact rational arithmetic.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from numbers import Real
from typing import Any

__all__ = [
    "ValidationError",
    "Tolerances",
    "DEFAULT_TOLERANCES",
    "to_decimal",
    "to_fraction",
    "validate_market_inputs",
    "validate_strike",
    "validate_cash_payout",
    "validate_payoffs",
    "relative_state_separation",
]


class ValidationError(ValueError):
    """Raised when inputs are mathematically invalid for the one-period model."""


@dataclass(frozen=True)
class Tolerances:
    """Numerical tolerance policy (all values are documented with their units).

    Attributes:
        near_boundary_relative_gap: Dimensionless. If the exact distance from
            ``R`` to the nearer of ``d`` or ``u``, divided by ``u - d``, is
            positive but below this value, the market is classified as
            ``near_boundary_unresolved`` instead of confidently arbitrage-free
            or arbitrage-containing. Exact equality is never "unresolved".
        min_relative_state_separation: Dimensionless, ``(u - d) / u``. Below
            this the two-state system is rejected as ill-conditioned.
        narrow_relative_state_separation: Dimensionless, ``(u - d) / u``.
            Below this a conditioning warning is attached but the model runs.
        payoff_abs_tol: Currency units. Used to decide whether an arbitrage
            portfolio's terminal payoff is nonnegative / strictly positive.
        quote_abs_tol: Currency units. Absolute part of the quote tolerance.
        quote_rel_tol: Dimensionless. Relative part of the quote tolerance,
            applied to ``max(|M|, |V|)``.
        replication_abs_tol: Currency units. Maximum acceptable absolute
            replication error per state for a replication check to "pass".
    """

    near_boundary_relative_gap: float = 1e-10
    min_relative_state_separation: float = 1e-12
    narrow_relative_state_separation: float = 1e-6
    payoff_abs_tol: float = 1e-9
    quote_abs_tol: float = 1e-9
    quote_rel_tol: float = 1e-9
    replication_abs_tol: float = 1e-9

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValidationError(f"Tolerance '{name}' must be a finite nonnegative number, got {value!r}")

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None) -> "Tolerances":
        """Build tolerances from a configuration mapping, ignoring nothing silently."""
        if not mapping:
            return cls()
        unknown = set(mapping) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValidationError(f"Unknown tolerance keys: {sorted(unknown)}")
        return cls(**{k: float(v) for k, v in mapping.items()})

    def to_dict(self) -> dict[str, float]:
        """Return the tolerances as a plain dictionary."""
        return asdict(self)


DEFAULT_TOLERANCES = Tolerances()


def to_decimal(value: Any, name: str) -> Decimal:
    """Convert a numeric input to an exact, finite :class:`Decimal`.

    Args:
        value: ``Decimal``, ``int``, ``float``, ``Fraction``-free real number or
            numeric string. Booleans are rejected.
        name: Parameter name used in error messages.

    Raises:
        ValidationError: If the value is not a finite number.
    """
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"{name} must be a finite number, got {value!r}")
    try:
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, int):
            result = Decimal(value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValidationError(f"{name} must be finite, got {value!r}")
            result = Decimal(repr(value))
        elif isinstance(value, str):
            result = Decimal(value.strip())
        elif isinstance(value, Real):
            as_float = float(value)
            if not math.isfinite(as_float):
                raise ValidationError(f"{name} must be finite, got {value!r}")
            result = Decimal(repr(as_float))
        else:
            raise ValidationError(f"{name} must be a finite number, got {type(value).__name__}")
    except (InvalidOperation, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"{name} must be a finite number, got {value!r}") from exc
    if not result.is_finite():
        raise ValidationError(f"{name} must be finite, got {value!r}")
    return result


def to_fraction(value: Decimal) -> Fraction:
    """Exact rational representation of a finite Decimal."""
    return Fraction(value)


def relative_state_separation(u: Decimal, d: Decimal) -> Fraction:
    """Exact dimensionless state separation ``(u - d) / u`` (requires ``u > 0``)."""
    return (to_fraction(u) - to_fraction(d)) / to_fraction(u)


def validate_market_inputs(
    S0: Any,
    u: Any,
    d: Any,
    r: Any,
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> tuple[Decimal, Decimal, Decimal, Decimal, list[str]]:
    """Validate the market inputs and return exact Decimals plus warnings.

    Required: all finite, ``S0 > 0``, ``u > d > 0``, ``r > -1``. Not required
    (deliberately): ``u > 1``, ``d < 1`` or ``r >= 0``.

    Returns:
        ``(S0, u, d, r, warnings)`` with Decimal values.

    Raises:
        ValidationError: For any invalid or ill-conditioned input.
    """
    S0_d = to_decimal(S0, "S0")
    u_d = to_decimal(u, "u")
    d_d = to_decimal(d, "d")
    r_d = to_decimal(r, "r")
    warnings: list[str] = []

    if S0_d <= 0:
        raise ValidationError(f"S0 must be > 0, got {S0_d}")
    if d_d <= 0:
        raise ValidationError(f"d must be > 0, got {d_d}")
    if u_d == d_d:
        raise ValidationError(
            f"u == d == {u_d}: degenerate single-state market, outside the two-distinct-state scope"
        )
    if u_d < d_d:
        raise ValidationError(f"u must be > d (up state is the higher terminal price), got u={u_d}, d={d_d}")
    if r_d <= -1:
        raise ValidationError(f"r must be > -1 so that R = 1 + r > 0, got r={r_d}")

    separation = relative_state_separation(u_d, d_d)
    if separation < Fraction(tolerances.min_relative_state_separation):
        raise ValidationError(
            "ill-conditioned state separation: (u - d)/u = "
            f"{float(separation):.3e} is below the conditioning limit "
            f"{tolerances.min_relative_state_separation:.1e}; replication would divide by a near-zero "
            "denominator"
        )
    if separation < Fraction(tolerances.narrow_relative_state_separation):
        warnings.append(
            "narrow_state_separation: (u - d)/u = "
            f"{float(separation):.3e} < {tolerances.narrow_relative_state_separation:.1e}; "
            "replication positions can be large relative to payoffs and results are sensitive to input rounding"
        )
    return S0_d, u_d, d_d, r_d, warnings


def validate_strike(K: Any) -> Decimal:
    """Validate a strike: finite and ``K >= 0`` (``K = 0`` is allowed)."""
    K_d = to_decimal(K, "K")
    if K_d < 0:
        raise ValidationError(f"K must be >= 0, got {K_d}")
    return K_d


def validate_cash_payout(cash_payout: Any) -> Decimal:
    """Validate a digital payout amount: finite and ``>= 0``."""
    p = to_decimal(cash_payout, "cash_payout")
    if p < 0:
        raise ValidationError(f"cash_payout must be >= 0, got {p}")
    return p


def validate_payoffs(payoff_up: Any, payoff_down: Any) -> tuple[float, float]:
    """Validate generic terminal payoffs: any finite values (negative allowed)."""
    xu = to_decimal(payoff_up, "payoff_up")
    xd = to_decimal(payoff_down, "payoff_down")
    return float(xu), float(xd)
