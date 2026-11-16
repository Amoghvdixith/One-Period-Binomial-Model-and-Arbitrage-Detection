"""Static Matplotlib charts (PNG). Uses the non-interactive Agg backend.

Every figure states the rate convention, masks invalid regions instead of
interpolating across them, and is closed after saving.

Colours follow a colour-vision-deficiency-checked categorical order
(blue, orange, aqua) with neutral grey for invalid regions and a single-hue
blue ramp for the sequential heatmap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Patch  # noqa: E402

from .sensitivity import STATUS_CODES, grid_matrix  # noqa: E402

__all__ = [
    "plot_tree",
    "plot_replication_payoffs",
    "plot_price_vs_strike",
    "plot_hedge_ratio_vs_strike",
    "plot_price_vs_rate",
    "plot_arbitrage_regions",
    "plot_call_price_heatmap",
]

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
VIOLET = "#6250d6"
GREY = "#c9c8c3"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
SURFACE = "#fcfcfb"
GRID = "#e4e3df"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

CONVENTION_NOTE = "Rate convention: r = effective simple one-period return, R = 1 + r (no annualisation)."

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": TEXT_2,
        "axes.labelcolor": TEXT,
        "xtick.color": TEXT_2,
        "ytick.color": TEXT_2,
        "text.color": TEXT,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 12,
        "legend.frameon": False,
    }
)


def _finish(fig: plt.Figure, path: Path) -> Path:
    fig.text(0.01, -0.035, CONVENTION_NOTE, fontsize=8, color=TEXT_2, ha="left", va="top")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_tree(market: dict[str, float], q: float | None, payoffs: dict[str, tuple[float, float]], path: Path) -> Path:
    """One-period stock tree annotated with S0, Su, Sd, q, 1-q and claim payoffs."""
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.set_axis_off()
    nodes = {"S0": (0.12, 0.5), "Su": (0.62, 0.82), "Sd": (0.62, 0.18)}
    box = dict(boxstyle="round,pad=0.5", fc="white", ec=TEXT_2, lw=1.2)
    ax.text(*nodes["S0"], f"S0 = {market['S0']:g}", ha="center", va="center", fontsize=12, bbox=box)
    ax.text(*nodes["Su"], f"Su = S0·u = {market['Su']:g}", ha="center", va="center", fontsize=12, bbox=box)
    ax.text(*nodes["Sd"], f"Sd = S0·d = {market['Sd']:g}", ha="center", va="center", fontsize=12, bbox=box)
    for end, label, y_off in (("Su", "q", 0.09), ("Sd", "1 − q", -0.09)):
        arrow = FancyArrowPatch(
            (nodes["S0"][0] + 0.08, nodes["S0"][1]),
            (nodes[end][0] - 0.14, nodes[end][1]),
            arrowstyle="-|>",
            mutation_scale=14,
            color=TEXT_2,
            lw=1.5,
        )
        ax.add_patch(arrow)
        mid_x = (nodes["S0"][0] + nodes[end][0]) / 2 - 0.09
        mid_y = (nodes["S0"][1] + nodes[end][1]) / 2 + y_off
        prob = "" if q is None else (f" = {q:.4g}" if label == "q" else f" = {1 - q:.4g}")
        ax.text(mid_x, mid_y, f"{label}{prob}", ha="center", va="center", fontsize=11, color=BLUE)
    up_lines = [f"{name}: {vals[0]:.4g}" for name, vals in payoffs.items()]
    down_lines = [f"{name}: {vals[1]:.4g}" for name, vals in payoffs.items()]
    ax.text(0.84, 0.82, "Up-state payoffs\n" + "\n".join(up_lines), ha="left", va="center", fontsize=10)
    ax.text(0.84, 0.18, "Down-state payoffs\n" + "\n".join(down_lines), ha="left", va="center", fontsize=10)
    ax.text(
        0.12,
        0.92,
        f"u = {market['u']:g}, d = {market['d']:g}, r = {market['r']:g}, R = {market['R']:g}",
        ha="left",
        fontsize=10,
        color=TEXT_2,
    )
    ax.text(0.12, 0.08, "q = (R − d)/(u − d) is a risk-neutral probability, not a real-world one.", fontsize=9, color=TEXT_2)
    ax.set_xlim(0, 1.1)
    ax.set_ylim(0, 1)
    ax.set_title("One-period stock tree with claim payoffs (baseline)")
    return _finish(fig, path)


def plot_replication_payoffs(checks: pd.DataFrame, path: Path) -> Path:
    """Claim payoff versus replicating-portfolio payoff, per claim and state."""
    n = len(checks)
    fig, axes = plt.subplots(1, n, figsize=(4.0 * n, 4.4), squeeze=False)
    width = 0.36
    for ax, (_, row) in zip(axes[0], checks.iterrows()):
        x = np.arange(2)
        claim_vals = [row["payoff_up"], row["payoff_down"]]
        rep_vals = [row["portfolio_up"], row["portfolio_down"]]
        ax.bar(x - width / 2 - 0.01, claim_vals, width, color=BLUE, label="Claim payoff")
        ax.bar(x + width / 2 + 0.01, rep_vals, width, color=ORANGE, label="Replicating portfolio ΔS₁ + BR")
        ax.set_xticks(x, ["Up state", "Down state"])
        ax.axhline(0, color=TEXT_2, lw=0.8)
        ax.set_title(str(row["claim"]))
        ax.set_ylabel("Terminal value (currency units)")
        ax.text(
            0.5,
            0.97,
            f"Δ = {row['delta']:.4g}, B = {row['cash_B']:.4g}\nmax |error| = {row['max_abs_error']:.2e}",
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9,
            color=TEXT_2,
        )
        lo = min(0.0, *claim_vals, *rep_vals)
        hi = max(0.0, *claim_vals, *rep_vals)
        ax.set_ylim(lo - 0.1 * (hi - lo + 1), hi + 0.35 * (hi - lo + 1))
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.suptitle("Claim payoffs vs replicating-portfolio payoffs (baseline market)", y=1.08)
    fig.legend(handles, labels, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.03), fontsize=9)
    fig.tight_layout()
    return _finish(fig, path)


def plot_price_vs_strike(sweep: pd.DataFrame, S0: float, path: Path) -> Path:
    """Call and put arbitrage-free prices versus strike."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(sweep["strike"], sweep["call_arbitrage_free_price"], color=BLUE, lw=2, label="Call")
    ax.plot(sweep["strike"], sweep["put_arbitrage_free_price"], color=ORANGE, lw=2, label="Put")
    ax.axvline(S0, color=TEXT_2, lw=1, ls=":")
    ax.text(S0, ax.get_ylim()[1] * 0.97, " K = S0", color=TEXT_2, va="top", fontsize=9)
    ax.set_xlabel("Strike K (currency units)")
    ax.set_ylabel("Arbitrage-free price (currency units)")
    ax.set_title("European call and put price versus strike (baseline market)")
    ax.legend(loc="center right")
    return _finish(fig, path)


def plot_hedge_ratio_vs_strike(sweep: pd.DataFrame, market: dict[str, float], path: Path) -> Path:
    """Replication hedge ratio (shares of stock) versus strike."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(sweep["strike"], sweep["call_replication_hedge_ratio"], color=BLUE, lw=2, label="Call Δ")
    ax.plot(sweep["strike"], sweep["put_replication_hedge_ratio"], color=ORANGE, lw=2, label="Put Δ")
    for level, name in ((market["Sd"], "Sd"), (market["Su"], "Su")):
        ax.axvline(level, color=TEXT_2, lw=1, ls=":")
        ax.text(level, 0.92, f" K = {name} = {level:g}", color=TEXT_2, fontsize=9, va="top")
    ax.axhline(0, color=TEXT_2, lw=0.8)
    ax.set_ylim(-1.1, 1.1)
    ax.set_xlabel("Strike K (currency units)")
    ax.set_ylabel("Replication hedge ratio Δ (shares per claim)")
    ax.set_title("Replication hedge ratio versus strike (exact one-period payoff matching)")
    ax.legend(loc="lower left")
    return _finish(fig, path)


def plot_price_vs_rate(sweep: pd.DataFrame, market: dict[str, float], path: Path) -> Path:
    """Call/put prices versus effective one-period rate, arbitrage regions shaded."""
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    r_lo = market["d"] - 1.0
    r_hi = market["u"] - 1.0
    xmin, xmax = sweep["r"].min(), sweep["r"].max()
    ax.axvspan(xmin, r_lo, color=GREY, alpha=0.45, lw=0)
    ax.axvspan(r_hi, xmax, color=GREY, alpha=0.45, lw=0)
    ax.axvline(r_lo, color=TEXT_2, lw=1.2, ls="--")
    ax.axvline(r_hi, color=TEXT_2, lw=1.2, ls="--")
    ax.plot(sweep["r"], sweep["call_arbitrage_free_price"], color=BLUE, lw=2, marker="o", ms=3, label="Call (K = baseline)")
    ax.plot(sweep["r"], sweep["put_arbitrage_free_price"], color=ORANGE, lw=2, marker="o", ms=3, label="Put (K = baseline)")
    top = np.nanmax(sweep[["call_arbitrage_free_price", "put_arbitrage_free_price"]].to_numpy())
    ax.set_ylim(0, top * 1.25)
    ax.text(r_lo, top * 1.2, f"R = d (r = {r_lo:.2f}) ", fontsize=9, va="top", ha="right", color=TEXT_2)
    ax.text(r_hi, top * 1.2, f" R = u (r = {r_hi:.2f})", fontsize=9, va="top", color=TEXT_2)
    ax.text((xmin + r_lo) / 2, top * 0.55, "R ≤ d:\narbitrage\n(no price shown)", ha="center", fontsize=9, color=TEXT_2)
    ax.text((r_hi + xmax) / 2, top * 0.55, "R ≥ u:\narbitrage\n(no price shown)", ha="center", fontsize=9, color=TEXT_2)
    ax.set_xlim(xmin, xmax)
    ax.set_xlabel("Effective one-period risk-free rate r")
    ax.set_ylabel("Arbitrage-free price (currency units)")
    ax.set_title("Option price versus effective one-period rate (prices only where d < R < u)")
    ax.legend(loc="upper center")
    return _finish(fig, path)


def _edges(values: np.ndarray) -> np.ndarray:
    step = np.diff(values).mean() if len(values) > 1 else 1.0
    return np.concatenate([values - step / 2, [values[-1] + step / 2]])


def _boundary_lines(ax: Any, R: float, u_vals: np.ndarray, d_vals: np.ndarray) -> None:
    lo = min(u_vals.min(), d_vals.min())
    hi = max(u_vals.max(), d_vals.max())
    ax.plot([lo, hi], [lo, hi], color=TEXT, lw=1.2, ls="-", label="u = d")
    ax.axvline(R, color=TEXT, lw=1.2, ls="--", label=f"d = R = {R:g}")
    ax.axhline(R, color=TEXT, lw=1.2, ls=":", label=f"u = R = {R:g}")
    ax.set_xlim(d_vals.min() - 0.005, d_vals.max() + 0.005)
    ax.set_ylim(u_vals.min() - 0.005, u_vals.max() + 0.005)


def plot_arbitrage_regions(grid: pd.DataFrame, R: float, baseline: dict[str, float], path: Path) -> Path:
    """Categorical map of market status over (d, u)."""
    u_vals, d_vals, codes = grid_matrix(grid, "status_code")
    colours = [GREY, BLUE, ORANGE, AQUA, VIOLET]
    cmap = ListedColormap(colours)
    norm = BoundaryNorm(np.arange(-0.5, len(colours) + 0.5), cmap.N)
    fig, ax = plt.subplots(figsize=(7.8, 6.8))
    ax.pcolormesh(_edges(d_vals), _edges(u_vals), codes, cmap=cmap, norm=norm, shading="flat")
    _boundary_lines(ax, R, u_vals, d_vals)
    ax.plot(baseline["d"], baseline["u"], marker="o", ms=9, mfc="white", mec=TEXT, mew=1.5, ls="none", label="Baseline (d=0.92, u=1.12)")
    present = set(grid["market_status"])
    labels = {
        "invalid_input": "Invalid input (u ≤ d), masked",
        "arbitrage_free": "Arbitrage-free (d < R < u)",
        "arbitrage_R_le_d": "Arbitrage: R ≤ d",
        "arbitrage_R_ge_u": "Arbitrage: R ≥ u",
        "near_boundary_unresolved": "Near boundary, unresolved",
    }
    handles = [Patch(color=colours[STATUS_CODES[s]], label=labels[s]) for s in labels if s in present]
    line_handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles=handles + line_handles, loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8.5)
    ax.grid(False)
    ax.set_xlabel("Down multiplier d")
    ax.set_ylabel("Up multiplier u")
    ax.set_title(f"No-arbitrage regions in (d, u) space (r fixed, R = {R:g})")
    return _finish(fig, path)


def plot_call_price_heatmap(grid: pd.DataFrame, R: float, K: float, baseline: dict[str, float], path: Path) -> Path:
    """Call price over the arbitrage-free (d, u) region; other cells masked."""
    u_vals, d_vals, prices = grid_matrix(grid, "call_arbitrage_free_price")
    masked = np.ma.masked_invalid(prices)
    cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE).with_extremes(bad=GREY)
    fig, ax = plt.subplots(figsize=(7.8, 6.8))
    mesh = ax.pcolormesh(_edges(d_vals), _edges(u_vals), masked, cmap=cmap, shading="flat")
    cbar = fig.colorbar(mesh, ax=ax, shrink=0.85)
    cbar.set_label(f"Call price, K = {K:g} (currency units)")
    _boundary_lines(ax, R, u_vals, d_vals)
    ax.plot(baseline["d"], baseline["u"], marker="o", ms=9, mfc="white", mec=TEXT, mew=1.5, ls="none", label="Baseline")
    handles, _ = ax.get_legend_handles_labels()
    handles.append(Patch(color=GREY, label="No arbitrage-free price (masked)"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=8.5)
    ax.grid(False)
    ax.set_xlabel("Down multiplier d")
    ax.set_ylabel("Up multiplier u")
    ax.set_title(f"Call price over the arbitrage-free (d, u) region (R = {R:g})")
    return _finish(fig, path)
