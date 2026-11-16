"""Sensitivity analysis tests."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from binomial_arbitrage import MarketParams
from binomial_arbitrage.sensitivity import decimal_range, grid_matrix, rate_sweep, strike_sweep, up_down_grid


def test_decimal_range_is_exact_and_inclusive():
    vals = decimal_range("-0.15", "0.20", "0.005")
    assert len(vals) == 71
    assert vals[0] == Decimal("-0.15") and vals[-1] == Decimal("0.2")
    assert Decimal("-0.08") in vals and Decimal("0.12") in vals


def test_strike_sweep_shape_and_monotonicity(baseline_params):
    df = strike_sweep(baseline_params, decimal_range(70, 130, 1))
    assert len(df) == 61
    call = df["call_arbitrage_free_price"].to_numpy()
    put = df["put_arbitrage_free_price"].to_numpy()
    assert np.all(np.diff(call) <= 1e-12), "call price must be nonincreasing in strike"
    assert np.all(np.diff(put) >= -1e-12), "put price must be nondecreasing in strike"
    assert np.abs(df["put_call_parity_residual"]).max() < 1e-10


def test_strike_sweep_hedge_ratios_hand_values(baseline_params):
    df = strike_sweep(baseline_params, [80, 100, 120]).set_index("strike")
    assert df.loc[80.0, "call_replication_hedge_ratio"] == pytest.approx(1.0)
    assert df.loc[100.0, "call_replication_hedge_ratio"] == pytest.approx(0.6)
    assert df.loc[120.0, "call_replication_hedge_ratio"] == pytest.approx(0.0)
    assert df.loc[120.0, "put_replication_hedge_ratio"] == pytest.approx(-1.0)


def test_strike_sweep_in_arbitrage_market_has_no_prices():
    params = MarketParams.create(100, Decimal("1.05"), Decimal("0.98"), Decimal("0.10"))
    df = strike_sweep(params, [90, 100])
    assert df["call_arbitrage_free_price"].isna().all()
    assert df["put_arbitrage_free_price"].isna().all()
    assert df["call_replication_hedge_ratio"].notna().all()


def test_rate_sweep_prices_only_where_permitted():
    rates = decimal_range("-0.15", "0.20", "0.005")
    df = rate_sweep(100, Decimal("1.12"), Decimal("0.92"), 100, rates)
    assert len(df) == len(rates)
    af = df["market_status"] == "arbitrage_free"
    assert df.loc[af, "call_arbitrage_free_price"].notna().all()
    assert df.loc[~af, "call_arbitrage_free_price"].isna().all()
    assert df.loc[~af, "put_arbitrage_free_price"].isna().all()
    # Arbitrage-free region is exactly -0.08 < r < 0.12.
    assert ((df["r"] > -0.08 + 1e-12) & (df["r"] < 0.12 - 1e-12)).eq(af).all()
    bnd = df.set_index("r")
    assert bnd.loc[-0.08, "exact_boundary"] == "R_equals_d"
    assert bnd.loc[0.12, "exact_boundary"] == "R_equals_u"


def test_rate_sweep_call_increasing_put_decreasing_in_r():
    df = rate_sweep(100, Decimal("1.12"), Decimal("0.92"), 100, decimal_range("-0.07", "0.11", "0.01"))
    assert np.all(np.diff(df["call_arbitrage_free_price"]) > 0)
    assert np.all(np.diff(df["put_arbitrage_free_price"]) < 0)


def test_up_down_grid_masking_and_shape():
    u_vals = decimal_range("0.80", "1.40", "0.05")
    d_vals = decimal_range("0.60", "1.20", "0.05")
    grid = up_down_grid(100, 100, Decimal("0.02"), u_vals, d_vals)
    assert len(grid) == len(u_vals) * len(d_vals)
    invalid = grid["u"] <= grid["d"]
    assert (~grid.loc[invalid, "valid_input"]).all()
    assert (grid.loc[invalid, "market_status"] == "invalid_input").all()
    assert grid.loc[invalid, ["call_arbitrage_free_price", "call_replication_hedge_ratio"]].isna().all().all()
    has_price = grid["call_arbitrage_free_price"].notna()
    assert (grid.loc[has_price, "market_status"] == "arbitrage_free").all()
    assert (grid.loc[grid["market_status"] == "arbitrage_free", "call_arbitrage_free_price"].notna()).all()
    # Every arbitrage-free cell satisfies d < 1.02 < u.
    af = grid[grid["market_status"] == "arbitrage_free"]
    assert ((af["d"] < 1.02) & (af["u"] > 1.02)).all()


def test_grid_matrix_pivot_shape():
    u_vals = decimal_range("0.9", "1.2", "0.1")
    d_vals = decimal_range("0.8", "1.0", "0.1")
    grid = up_down_grid(100, 100, Decimal("0.02"), u_vals, d_vals)
    u, d, m = grid_matrix(grid, "status_code")
    assert m.shape == (len(u_vals), len(d_vals))
    assert np.all(np.diff(u) > 0) and np.all(np.diff(d) > 0)
