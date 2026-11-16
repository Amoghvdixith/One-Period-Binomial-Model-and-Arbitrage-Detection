"""Sensitivity analysis: strike sweep, rate sweep and an (u, d) grid.

Rules followed by every table produced here:

* Prices are reported in ``*_arbitrage_free_price`` columns only where the
  market is strictly arbitrage-free; elsewhere the cell is empty (NaN).
* Hedge ratios are the exact one-period *replication hedge ratios*
  ``Delta = (Xu - Xd)/(Su - Sd)``. They are reported wherever the inputs are
  valid (the replication algebra does not need no-arbitrage), and they are not
  labelled "delta" in the sense of a spot derivative, nor is any gamma given.
* Grid points with ``u <= d`` are invalid inputs: status ``invalid_input``,
  ``valid_input = False`` and no values.

Sweep points are generated with exact ``Decimal`` steps so that boundary
points such as ``R = d`` are hit exactly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .model import MarketParams, MarketStatus, classify_inputs, classify_market
from .payoffs import ClaimSpec, terminal_payoffs
from .pricing import risk_neutral_price
from .replication import replicate
from .validation import DEFAULT_TOLERANCES, Tolerances, ValidationError, to_decimal

__all__ = ["decimal_range", "strike_sweep", "rate_sweep", "up_down_grid", "grid_matrix"]


def decimal_range(start: Any, stop: Any, step: Any) -> list[Decimal]:
    """Inclusive arithmetic sequence in exact Decimal arithmetic."""
    a, b, h = to_decimal(start, "start"), to_decimal(stop, "stop"), to_decimal(step, "step")
    if h <= 0:
        raise ValidationError(f"step must be > 0, got {h}")
    if b < a:
        raise ValidationError(f"stop must be >= start, got start={a}, stop={b}")
    n = int((b - a) / h)
    values = [a + i * h for i in range(n + 1)]
    if values[-1] != b and values[-1] + h <= b:
        values.append(values[-1] + h)
    return [v.normalize() if v != 0 else Decimal(0) for v in values]


def _price_or_nan(params: MarketParams, cls, spec: ClaimSpec, tol: Tolerances) -> tuple[float, float, float]:
    """Return (arbitrage-free price or NaN, replication hedge ratio, replication cash B)."""
    xu, xd = terminal_payoffs(params.S0, params.u, params.d, spec)
    rep = replicate(params, xu, xd, spec.label())
    if cls.is_arbitrage_free:
        price = risk_neutral_price(params, xu, xd, spec.label(), cls, tol).arbitrage_free_price
    else:
        price = float("nan")
    return float(price), rep.delta, rep.cash_B


def strike_sweep(
    params: MarketParams,
    strikes: Iterable[Any],
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> pd.DataFrame:
    """Call/put prices and replication hedge ratios as functions of strike."""
    cls = classify_market(params, tolerances)
    rows = []
    for K in strikes:
        K_d = to_decimal(K, "K")
        call = ClaimSpec.from_mapping({"type": "call", "K": K_d})
        put = ClaimSpec.from_mapping({"type": "put", "K": K_d})
        cu, cd = terminal_payoffs(params.S0, params.u, params.d, call)
        pu, pd_ = terminal_payoffs(params.S0, params.u, params.d, put)
        c_price, c_delta, c_B = _price_or_nan(params, cls, call, tolerances)
        p_price, p_delta, p_B = _price_or_nan(params, cls, put, tolerances)
        rows.append(
            {
                "strike": float(K_d),
                "market_status": cls.status.value,
                "call_payoff_up": cu,
                "call_payoff_down": cd,
                "put_payoff_up": pu,
                "put_payoff_down": pd_,
                "call_arbitrage_free_price": c_price,
                "put_arbitrage_free_price": p_price,
                "call_replication_hedge_ratio": c_delta,
                "put_replication_hedge_ratio": p_delta,
                "call_replication_cash_B": c_B,
                "put_replication_cash_B": p_B,
                "put_call_parity_residual": (c_price - p_price) - (float(params.S0) - float(K_d) / params.R),
                "warnings": "; ".join(cls.warnings),
            }
        )
    return pd.DataFrame(rows)


def rate_sweep(
    S0: Any,
    u: Any,
    d: Any,
    K: Any,
    rates: Iterable[Any],
    cash_payout: Any = 1,
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> pd.DataFrame:
    """Prices versus the effective one-period rate ``r`` (``R = 1 + r``)."""
    K_d = to_decimal(K, "K")
    call = ClaimSpec.from_mapping({"type": "call", "K": K_d})
    put = ClaimSpec.from_mapping({"type": "put", "K": K_d})
    dig = ClaimSpec.from_mapping({"type": "digital", "K": K_d, "cash_payout": cash_payout})
    rows = []
    for r in rates:
        params, cls = classify_inputs(S0, u, d, r, tolerances)
        r_d = to_decimal(r, "r")
        row: dict[str, Any] = {
            "r": float(r_d),
            "R": float(1 + r_d),
            "market_status": cls.status.value,
            "exact_boundary": cls.exact_boundary or "",
            "q_candidate": cls.q_candidate if cls.q_candidate is not None else float("nan"),
            "call_arbitrage_free_price": float("nan"),
            "put_arbitrage_free_price": float("nan"),
            "digital_arbitrage_free_price": float("nan"),
            "call_replication_hedge_ratio": float("nan"),
            "put_replication_hedge_ratio": float("nan"),
            "warnings": "; ".join(cls.warnings) if params is not None else cls.message,
        }
        if params is not None:
            c_price, c_delta, _ = _price_or_nan(params, cls, call, tolerances)
            p_price, p_delta, _ = _price_or_nan(params, cls, put, tolerances)
            d_price, _, _ = _price_or_nan(params, cls, dig, tolerances)
            row.update(
                call_arbitrage_free_price=c_price,
                put_arbitrage_free_price=p_price,
                digital_arbitrage_free_price=d_price,
                call_replication_hedge_ratio=c_delta,
                put_replication_hedge_ratio=p_delta,
            )
        rows.append(row)
    return pd.DataFrame(rows)


def up_down_grid(
    S0: Any,
    K: Any,
    r: Any,
    u_values: Iterable[Any],
    d_values: Iterable[Any],
    tolerances: Tolerances = DEFAULT_TOLERANCES,
) -> pd.DataFrame:
    """Classification and call price over a grid of (u, d) multipliers.

    Returns a long table with one row per (u, d) pair.
    """
    call = ClaimSpec.from_mapping({"type": "call", "K": K})
    rows = []
    for u in u_values:
        for d in d_values:
            u_d, d_d = to_decimal(u, "u"), to_decimal(d, "d")
            params, cls = classify_inputs(S0, u_d, d_d, r, tolerances)
            row: dict[str, Any] = {
                "u": float(u_d),
                "d": float(d_d),
                "valid_input": params is not None,
                "market_status": cls.status.value,
                "exact_boundary": cls.exact_boundary or "",
                "q_candidate": cls.q_candidate if cls.q_candidate is not None else float("nan"),
                "call_arbitrage_free_price": float("nan"),
                "call_replication_hedge_ratio": float("nan"),
                "warnings": "; ".join(cls.warnings) if params is not None else cls.message,
            }
            if params is not None:
                price, delta, _ = _price_or_nan(params, cls, call, tolerances)
                row["call_arbitrage_free_price"] = price
                row["call_replication_hedge_ratio"] = delta
            rows.append(row)
    return pd.DataFrame(rows)


STATUS_CODES = {
    MarketStatus.INVALID_INPUT.value: 0,
    MarketStatus.ARBITRAGE_FREE.value: 1,
    MarketStatus.ARBITRAGE_R_LE_D.value: 2,
    MarketStatus.ARBITRAGE_R_GE_U.value: 3,
    MarketStatus.NEAR_BOUNDARY_UNRESOLVED.value: 4,
}


def grid_matrix(grid: pd.DataFrame, column: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pivot a long grid table to ``(u_values, d_values, matrix[u_index, d_index])``.

    ``column="status_code"`` maps statuses through :data:`STATUS_CODES`.
    """
    df = grid.copy()
    if column == "status_code":
        df["status_code"] = df["market_status"].map(STATUS_CODES).astype(float)
    table = df.pivot(index="u", columns="d", values=column).sort_index().sort_index(axis=1)
    return table.index.to_numpy(dtype=float), table.columns.to_numpy(dtype=float), table.to_numpy(dtype=float)
