"""Experiment orchestration, deterministic file writers, metadata and report.

All writers overwrite their target atomically (write to a temporary file in
the same directory, then ``os.replace``), so repeated runs never append or
duplicate rows. No absolute or personal paths are recorded in any output.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import pandas as pd

from .arbitrage import quote_arbitrage, underlying_arbitrage
from .model import RATE_CONVENTION, MarketStatus, classify_inputs
from .payoffs import ClaimSpec, terminal_payoffs
from .pricing import risk_neutral_price, state_prices
from .replication import replicate
from .validation import Tolerances, ValidationError

__all__ = [
    "load_json",
    "write_json",
    "write_csv",
    "write_text",
    "claim_record",
    "market_record",
    "analyze_scenario",
    "run_experiments",
    "FIGURE_FILES",
    "OUTPUT_FILES",
]

FIGURE_FILES = (
    "one_period_tree.png",
    "replication_payoffs.png",
    "call_put_vs_strike.png",
    "hedge_ratio_vs_strike.png",
    "price_vs_rate.png",
    "arbitrage_regions.png",
    "call_price_heatmap.png",
)

OUTPUT_FILES = (
    "example_call.json",
    "example_put.json",
    "example_digital.json",
    "scenario_summary.csv",
    "replication_checks.csv",
    "underlying_arbitrage.csv",
    "quote_arbitrage.csv",
    "strike_sensitivity.csv",
    "rate_sensitivity.csv",
    "up_down_grid.csv",
    "run_metadata.json",
)


# --------------------------------------------------------------------------
# I/O helpers
# --------------------------------------------------------------------------
def load_json(path: Path) -> dict[str, Any]:
    """Load JSON with floats parsed as exact Decimals."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON in {path.name}: {exc}") from exc


def _sanitize(obj: Any) -> Any:
    """Convert to JSON-safe values: Decimal->float, NaN/inf->None, Enum->value."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "item"):  # numpy scalar
        return _sanitize(obj.item())
    return str(obj)


def _atomic_write_bytes(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return path


def write_json(path: Path, obj: Any) -> Path:
    """Write JSON deterministically (UTF-8, indent 2, ``\\n`` newlines, NaN -> null)."""
    text = json.dumps(_sanitize(obj), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return _atomic_write_bytes(path, text.encode("utf-8"))


def write_csv(path: Path, df: pd.DataFrame) -> Path:
    """Write a CSV (overwrite, no index, ``\\n`` newlines, NaN -> empty cell)."""
    text = df.to_csv(index=False, lineterminator="\n")
    return _atomic_write_bytes(path, text.encode("utf-8"))


def write_text(path: Path, text: str) -> Path:
    """Write UTF-8 text with ``\\n`` newlines."""
    return _atomic_write_bytes(path, text.encode("utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Record builders
# --------------------------------------------------------------------------
def _claim_from_baseline(baseline: dict[str, Any], claim_type: str) -> ClaimSpec:
    mapping: dict[str, Any] = {"type": claim_type, "K": baseline["K"]}
    if claim_type == "digital":
        mapping["cash_payout"] = baseline.get("cash_payout", 1)
    return ClaimSpec.from_mapping(mapping)


def _replication_passed(rep, tol: Tolerances) -> bool:
    scale = 1.0 + max(abs(rep.payoff_up), abs(rep.payoff_down))
    return rep.max_abs_error <= tol.replication_abs_tol * scale


def claim_record(market: dict[str, Any], spec: ClaimSpec, tol: Tolerances) -> dict[str, Any]:
    """Full JSON-ready analysis of one claim in one market (no timestamps)."""
    params, cls = classify_inputs(market["S0"], market["u"], market["d"], market["r"], tol)
    record: dict[str, Any] = {
        "model_convention": RATE_CONVENTION,
        "inputs": {k: market[k] for k in ("S0", "u", "d", "r")},
        "claim": {
            "type": spec.claim_type,
            "label": spec.label(),
            "K": spec.K,
            "cash_payout": spec.cash_payout,
            "digital_rule": "pays cash_payout if S_T > K (strict inequality)" if spec.claim_type == "digital" else None,
        },
        "classification": cls.to_dict(),
    }
    if params is None:
        record["error"] = cls.message
        return record
    xu, xd = terminal_payoffs(params.S0, params.u, params.d, spec)
    pricing = risk_neutral_price(params, xu, xd, spec.label(), cls, tol)
    rep = replicate(params, xu, xd, spec.label())
    record["derived"] = {"R": params.R, "Su": params.Su, "Sd": params.Sd}
    record["terminal_payoffs"] = {"up": xu, "down": xd}
    record["pricing"] = pricing.to_dict()
    record["replication"] = rep.to_dict()
    record["replication_check_passed"] = _replication_passed(rep, tol)
    if pricing.arbitrage_free_price is not None:
        record["price_minus_replication_cost"] = pricing.arbitrage_free_price - rep.initial_cost
    record["underlying_arbitrage"] = underlying_arbitrage(params, cls, tol).to_dict()
    return record


def market_record(market: dict[str, Any], tol: Tolerances) -> dict[str, Any]:
    """JSON-ready analysis of the stock/cash market plus call, put and digital."""
    params, cls = classify_inputs(market["S0"], market["u"], market["d"], market["r"], tol)
    out: dict[str, Any] = {
        "model_convention": RATE_CONVENTION,
        "inputs": {k: market[k] for k in ("S0", "u", "d", "r", "K") if k in market},
        "classification": cls.to_dict(),
    }
    if params is None:
        out["error"] = cls.message
        return out
    out["derived"] = params.as_floats()
    sp = state_prices(params, cls)
    out["state_prices"] = sp.to_dict() if sp else None
    out["underlying_arbitrage"] = underlying_arbitrage(params, cls, tol).to_dict()
    claims = {}
    for claim_type in ("call", "put", "digital"):
        spec = _claim_from_baseline(market, claim_type)
        rec = claim_record(market, spec, tol)
        claims[claim_type] = {
            "terminal_payoffs": rec["terminal_payoffs"],
            "arbitrage_free_price": rec["pricing"]["arbitrage_free_price"],
            "algebraic_replication_cost": rec["pricing"]["algebraic_replication_cost"],
            "replication_hedge_ratio": rec["replication"]["delta"],
            "replication_cash_B": rec["replication"]["cash_B"],
            "max_abs_replication_error": rec["replication"]["max_abs_error"],
        }
    out["claims"] = claims
    c, p = claims["call"]["arbitrage_free_price"], claims["put"]["arbitrage_free_price"]
    if c is not None and p is not None:
        out["put_call_parity"] = {
            "C_minus_P": c - p,
            "S0_minus_K_over_R": float(params.S0) - float(Decimal(str(market["K"]))) / params.R,
            "residual": (c - p) - (float(params.S0) - float(Decimal(str(market["K"]))) / params.R),
        }
    return out


def analyze_scenario(scn: dict[str, Any], tol: Tolerances) -> dict[str, Any]:
    """Evaluate one scenario; returns rows for each output table."""
    sid = str(scn["id"])
    spec = ClaimSpec.from_mapping(scn["claim"])
    params, cls = classify_inputs(scn["S0"], scn["u"], scn["d"], scn["r"], tol)
    quoted = scn.get("quoted_price")
    base = {
        "scenario_id": sid,
        "description": scn.get("description", ""),
        "claim": spec.label(),
        "claim_type": spec.claim_type,
        "S0": float(scn["S0"]),
        "u": float(scn["u"]),
        "d": float(scn["d"]),
        "r": float(scn["r"]),
        "R": float(1 + Decimal(str(scn["r"]))),
        "K": float(spec.K) if spec.K is not None else float("nan"),
        "cash_payout": float(spec.cash_payout) if spec.cash_payout is not None else float("nan"),
        "market_status": cls.status.value,
        "exact_boundary": cls.exact_boundary or "",
        "q_candidate": cls.q_candidate if cls.q_candidate is not None else float("nan"),
        "q_is_risk_neutral_probability": cls.is_arbitrage_free,
    }
    out: dict[str, Any] = {"summary": None, "replication": None, "underlying": None, "quote": [], "warnings": [], "failures": []}
    if params is None:
        out["summary"] = {**base, "error_message": cls.message, "warnings": ""}
        return out

    xu, xd = terminal_payoffs(params.S0, params.u, params.d, spec)
    pricing = risk_neutral_price(params, xu, xd, spec.label(), cls, tol)
    rep = replicate(params, xu, xd, spec.label())
    arb = underlying_arbitrage(params, cls, tol)
    rep_ok = _replication_passed(rep, tol)
    price = pricing.arbitrage_free_price

    summary = {
        **base,
        "payoff_up": xu,
        "payoff_down": xd,
        "arbitrage_free_price": price if price is not None else float("nan"),
        "algebraic_replication_cost_not_arbitrage_free": (
            pricing.algebraic_replication_cost if pricing.algebraic_replication_cost is not None else float("nan")
        ),
        "replication_hedge_ratio": rep.delta,
        "replication_cash_B": rep.cash_B,
        "max_abs_replication_error": rep.max_abs_error,
        "replication_check_passed": rep_ok,
        "underlying_arbitrage_case": arb.case or "",
        "underlying_arbitrage_verified": arb.verified,
        "quoted_price": float(quoted) if quoted is not None else float("nan"),
        "quote_direction": "",
        "quote_arbitrage_verified": False,
        "quote_profit_per_unit": float("nan"),
        "warnings": "; ".join(cls.warnings),
        "error_message": "",
    }
    out["replication"] = {
        "scenario_id": sid,
        "claim": spec.label(),
        "market_status": cls.status.value,
        **{k: v for k, v in rep.to_dict().items() if k != "claim_name"},
        "check_tolerance": tol.replication_abs_tol * (1.0 + max(abs(xu), abs(xd))),
        "check_passed": rep_ok,
        "arbitrage_free_price": price if price is not None else float("nan"),
        "price_minus_replication_cost": (price - rep.initial_cost) if price is not None else float("nan"),
    }
    out["underlying"] = {"scenario_id": sid, **arb.to_dict()}
    if cls.warnings:
        out["warnings"].extend(f"{sid}: {w}" for w in cls.warnings)
    if not rep_ok:
        out["failures"].append(f"{sid}: replication error {rep.max_abs_error:.3e} exceeds tolerance")
    if cls.contains_arbitrage and not arb.verified:
        out["failures"].append(f"{sid}: arbitrage market but arbitrage portfolio not verified")

    if quoted is not None:
        q = quote_arbitrage(params, cls, xu, xd, float(quoted), spec.label(), tol)
        summary["quote_direction"] = q.direction
        summary["quote_arbitrage_verified"] = q.verified
        summary["quote_profit_per_unit"] = q.expected_profit if q.expected_profit is not None else float("nan")
        head = {
            "scenario_id": sid,
            "claim": spec.label(),
            "market_status": cls.status.value,
            "quoted_price": q.quoted_price,
            "replication_cost": q.replication_cost if q.replication_cost is not None else float("nan"),
            "difference": q.difference if q.difference is not None else float("nan"),
            "tolerance": q.tolerance if q.tolerance is not None else float("nan"),
            "direction": q.direction,
        }
        for leg in q.legs:
            out["quote"].append({**head, "row_type": "leg", "leg": leg.leg, "quantity": leg.quantity,
                                 "time0_cashflow": leg.time0_cashflow, "payoff_up": leg.payoff_up,
                                 "payoff_down": leg.payoff_down, "verified": "", "message": ""})
        out["quote"].append({
            **head,
            "row_type": "net",
            "leg": "NET (initial cost = -sum of time-0 cashflows)",
            "quantity": float("nan"),
            "time0_cashflow": (-q.initial_net_cost + 0.0) if q.initial_net_cost is not None else float("nan"),
            "payoff_up": q.net_payoff_up if q.net_payoff_up is not None else float("nan"),
            "payoff_down": q.net_payoff_down if q.net_payoff_down is not None else float("nan"),
            "verified": q.verified,
            "message": q.message,
        })
        if q.direction in ("overpriced", "underpriced") and not q.verified:
            out["failures"].append(f"{sid}: quote arbitrage not verified")
    out["summary"] = summary
    return out


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def _dependency_versions() -> dict[str, str]:
    versions = {}
    for pkg in ("numpy", "pandas", "matplotlib", "pytest"):
        try:
            versions[pkg] = importlib_metadata.version(pkg)
        except importlib_metadata.PackageNotFoundError:
            versions[pkg] = "not installed"
    return versions


def load_experiment_config(config_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Load the scenario config and its referenced baseline config."""
    config_path = Path(config_path)
    config = load_json(config_path)
    for key in ("scenarios", "sensitivity", "baseline_config"):
        if key not in config:
            raise ValidationError(f"{config_path.name} is missing required key '{key}'")
    baseline_path = config_path.parent / str(config["baseline_config"])
    baseline = load_json(baseline_path)
    for key in ("S0", "u", "d", "r", "K"):
        if key not in baseline:
            raise ValidationError(f"{baseline_path.name} is missing required key '{key}'")
    ids = [str(s.get("id")) for s in config["scenarios"]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValidationError(f"Duplicate scenario ids: {dupes}")
    return config, baseline, baseline_path


def run_experiments(config_path: Path, output_dir: Path, make_figures: bool = True) -> dict[str, Any]:
    """Run every scenario and sensitivity analysis and write all outputs.

    Returns the run metadata dictionary (also written to run_metadata.json).
    """
    from . import plotting
    from .model import MarketParams
    from .sensitivity import decimal_range, rate_sweep, strike_sweep, up_down_grid

    config_path = Path(config_path)
    output_dir = Path(output_dir)
    config, baseline, baseline_path = load_experiment_config(config_path)
    tol = Tolerances.from_mapping(config.get("tolerances"))
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries, replications, underlyings, quotes = [], [], [], []
    warnings: list[str] = []
    failures: list[str] = []
    rejected: list[dict[str, str]] = []
    for scn in config["scenarios"]:
        res = analyze_scenario(scn, tol)
        summaries.append(res["summary"])
        if res["replication"]:
            replications.append(res["replication"])
        if res["underlying"]:
            underlyings.append(res["underlying"])
        quotes.extend(res["quote"])
        warnings.extend(res["warnings"])
        failures.extend(res["failures"])
        if res["summary"]["market_status"] == MarketStatus.INVALID_INPUT.value:
            rejected.append({"scenario_id": res["summary"]["scenario_id"], "reason": res["summary"]["error_message"]})

    write_csv(output_dir / "scenario_summary.csv", pd.DataFrame(summaries))
    write_csv(output_dir / "replication_checks.csv", pd.DataFrame(replications))
    write_csv(output_dir / "underlying_arbitrage.csv", pd.DataFrame(underlyings))
    write_csv(output_dir / "quote_arbitrage.csv", pd.DataFrame(quotes))

    examples = {}
    for claim_type in ("call", "put", "digital"):
        rec = claim_record(baseline, _claim_from_baseline(baseline, claim_type), tol)
        examples[claim_type] = rec
        write_json(output_dir / f"example_{claim_type}.json", rec)

    sens = config["sensitivity"]
    base_params = MarketParams.create(baseline["S0"], baseline["u"], baseline["d"], baseline["r"], tol)
    strikes = decimal_range(sens["strike"]["start"], sens["strike"]["stop"], sens["strike"]["step"])
    rates = decimal_range(sens["rate"]["start"], sens["rate"]["stop"], sens["rate"]["step"])
    g = sens["grid"]
    u_values = decimal_range(g["u_start"], g["u_stop"], g["u_step"])
    d_values = decimal_range(g["d_start"], g["d_stop"], g["d_step"])
    strike_df = strike_sweep(base_params, strikes, tol)
    rate_df = rate_sweep(baseline["S0"], baseline["u"], baseline["d"], baseline["K"], rates, baseline.get("cash_payout", 1), tol)
    grid_df = up_down_grid(baseline["S0"], baseline["K"], baseline["r"], u_values, d_values, tol)
    write_csv(output_dir / "strike_sensitivity.csv", strike_df)
    write_csv(output_dir / "rate_sensitivity.csv", rate_df)
    write_csv(output_dir / "up_down_grid.csv", grid_df)

    figures: list[str] = []
    if make_figures:
        fig_dir = output_dir / "figures"
        market = base_params.as_floats()
        call_rec = examples["call"]
        payoffs = {
            f"Call K={float(baseline['K']):g}": tuple(examples["call"]["terminal_payoffs"].values()),
            f"Put K={float(baseline['K']):g}": tuple(examples["put"]["terminal_payoffs"].values()),
            f"Digital (pays {float(baseline.get('cash_payout', 1)):g} if S>K)": tuple(examples["digital"]["terminal_payoffs"].values()),
        }
        plotting.plot_tree(market, call_rec["pricing"]["risk_neutral_q"], payoffs, fig_dir / "one_period_tree.png")
        rep_rows = pd.DataFrame(
            [
                {"claim": title, **examples[t]["replication"]}
                for t, title in (
                    ("call", f"European call, K = {float(baseline['K']):g}"),
                    ("put", f"European put, K = {float(baseline['K']):g}"),
                    ("digital", f"Digital call, K = {float(baseline['K']):g}, payout {float(baseline.get('cash_payout', 1)):g}"),
                )
            ]
        )
        plotting.plot_replication_payoffs(rep_rows, fig_dir / "replication_payoffs.png")
        plotting.plot_price_vs_strike(strike_df, market["S0"], fig_dir / "call_put_vs_strike.png")
        plotting.plot_hedge_ratio_vs_strike(strike_df, market, fig_dir / "hedge_ratio_vs_strike.png")
        plotting.plot_price_vs_rate(rate_df, market, fig_dir / "price_vs_rate.png")
        plotting.plot_arbitrage_regions(grid_df, market["R"], market, fig_dir / "arbitrage_regions.png")
        plotting.plot_call_price_heatmap(grid_df, market["R"], float(baseline["K"]), market, fig_dir / "call_price_heatmap.png")
        figures = [f"figures/{name}" for name in FIGURE_FILES]

    status_counts = pd.Series([s["market_status"] for s in summaries]).value_counts().sort_index().to_dict()
    meta = {
        "project": "One-Period Binomial Model and Arbitrage Detection",
        "package_version": _package_version(),
        "model_convention": RATE_CONVENTION,
        "continuous_rate_conversion_note": "If starting from a continuous annual rate rc and maturity T: R = exp(rc*T), r = R - 1 (documented, not implemented).",
        "execution_timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.system(),
        "dependency_versions": _dependency_versions(),
        "tolerances": tol.to_dict(),
        "config_files": {
            config_path.name: {"sha256": _sha256(config_path)},
            baseline_path.name: {"sha256": _sha256(baseline_path)},
        },
        "input_configurations": {"baseline": baseline, "scenarios": config},
        "counts": {
            "scenarios": len(summaries),
            "scenarios_by_status": status_counts,
            "rejected_invalid_input": len(rejected),
            "replication_checks": len(replications),
            "replication_checks_passed": sum(bool(r["check_passed"]) for r in replications),
            "underlying_arbitrage_verified": sum(bool(u["verified"]) for u in underlyings),
            "underlying_arbitrage_verified_in_arbitrage_markets": sum(
                bool(u["verified"]) and u["market_status"] in ("arbitrage_R_le_d", "arbitrage_R_ge_u") for u in underlyings
            ),
            "underlying_candidates_verified_in_unresolved_markets": sum(
                bool(u["verified"]) and u["market_status"] == "near_boundary_unresolved" for u in underlyings
            ),
            "arbitrage_markets": sum(
                s["market_status"] in ("arbitrage_R_le_d", "arbitrage_R_ge_u") for s in summaries
            ),
            "quote_scenarios": sum(1 for s in summaries if s.get("quote_direction")),
            "quote_arbitrage_verified": sum(bool(s.get("quote_arbitrage_verified")) for s in summaries),
            "strike_points": len(strike_df),
            "rate_points": len(rate_df),
            "grid_points": len(grid_df),
            "grid_points_with_arbitrage_free_price": int(grid_df["call_arbitrage_free_price"].notna().sum()),
        },
        "max_abs_replication_error": max((r["max_abs_error"] for r in replications), default=None),
        "expected_rejections": rejected,
        "warnings": warnings,
        "failures": failures,
        "outputs": list(OUTPUT_FILES) + figures,
        "randomness": "none (deterministic; no Monte Carlo)",
    }
    write_json(output_dir / "run_metadata.json", meta)
    return meta


# --------------------------------------------------------------------------
# Research report (rendered only from saved result files)
# --------------------------------------------------------------------------
def fmt(x: Any, spec: str = ".6f") -> str:
    """Format a number for the report; missing values become an em dash."""
    if x is None or (isinstance(x, float) and math.isnan(x)) or (isinstance(x, str) and x == ""):
        return "—"
    try:
        if pd.isna(x):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(x, (bool,)) or str(x) in ("True", "False"):
        return "yes" if str(x) == "True" else "no"
    try:
        return format(float(x), spec)
    except (TypeError, ValueError):
        return str(x)


def _md_table(df: pd.DataFrame, formats: dict[str, str] | None = None) -> str:
    formats = formats or {}
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if c in formats:
                cells.append(fmt(v, formats[c]))
            elif isinstance(v, (float, int)) and not isinstance(v, bool):
                cells.append(fmt(v, ".6g"))
            else:
                cells.append(fmt(v) if (v is None or (isinstance(v, float) and math.isnan(v))) else str(v).replace("|", "/"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def read_test_summary(results_dir: Path) -> dict[str, int] | None:
    """Parse pytest's JUnit XML (if present) into pass/fail/skip/error counts."""
    import xml.etree.ElementTree as ET

    path = Path(results_dir) / "test_results.xml"
    if not path.is_file():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = sum(int(s.get("tests", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return {"tests": total, "passed": total - failures - errors - skipped, "failed": failures, "errors": errors, "skipped": skipped}


def build_report(results_dir: Path) -> str:
    """Render the Markdown research report from the saved CSV/JSON outputs."""
    results_dir = Path(results_dir)
    meta = json.loads((results_dir / "run_metadata.json").read_text(encoding="utf-8"))
    examples = {t: json.loads((results_dir / f"example_{t}.json").read_text(encoding="utf-8")) for t in ("call", "put", "digital")}
    summary = pd.read_csv(results_dir / "scenario_summary.csv")
    rep = pd.read_csv(results_dir / "replication_checks.csv")
    und = pd.read_csv(results_dir / "underlying_arbitrage.csv")
    quotes = pd.read_csv(results_dir / "quote_arbitrage.csv")
    strike = pd.read_csv(results_dir / "strike_sensitivity.csv")
    rate = pd.read_csv(results_dir / "rate_sensitivity.csv")
    grid = pd.read_csv(results_dir / "up_down_grid.csv")
    tests = read_test_summary(results_dir)
    counts = meta["counts"]
    base_in = examples["call"]["inputs"]
    derived = examples["call"]["derived"]
    q = examples["call"]["pricing"]["risk_neutral_q"]
    sp = examples["call"]["pricing"]["state_prices"]

    L: list[str] = []
    a = L.append
    a("# Research Report: One-Period Binomial Model and Arbitrage Detection")
    a("")
    a(f"*Generated by `scripts/generate_report.py` from the saved files in this folder. Experiment run (UTC): "
      f"{meta['execution_timestamp_utc']}; Python {meta['python_version']}; "
      + ", ".join(f"{k} {v}" for k, v in meta["dependency_versions"].items()) + ".*")
    a("")
    a("## 1. Overview")
    a("")
    a("This report summarises an educational one-period, two-state market with one stock and one risk-free cash account. "
      "It classifies markets by the strict no-arbitrage condition d < R < u, prices claims by risk-neutral valuation and "
      "state prices where (and only where) the market is arbitrage-free, verifies exact stock-and-cash replication state by "
      "state, constructs explicit arbitrage portfolios for invalid markets and mispriced quotes, and runs strike, rate and "
      "(u, d) sensitivity analyses. All numbers below are read from the CSV/JSON files produced by "
      "`scripts/run_experiments.py`; nothing is hard-coded.")
    a("")
    a(f"- Scenarios evaluated: **{counts['scenarios']}** "
      f"({', '.join(f'{k}: {v}' for k, v in counts['scenarios_by_status'].items())}).")
    a(f"- Replication checks passed: **{counts['replication_checks_passed']} / {counts['replication_checks']}**; "
      f"maximum absolute replication error **{fmt(meta['max_abs_replication_error'], '.3e')}** currency units.")
    a(f"- Run warnings: {len(meta['warnings'])}; run failures: {len(meta['failures'])}.")
    if tests:
        a(f"- Automated tests (from `test_results.xml`): {tests['tests']} collected, {tests['passed']} passed, "
          f"{tests['failed']} failed, {tests['errors']} errors, {tests['skipped']} skipped.")
    else:
        a("- Automated tests: `test_results.xml` not present when this report was generated.")
    a("")
    a("## 2. Model configuration")
    a("")
    a(f"**Rate convention.** {meta['model_convention']} {meta['continuous_rate_conversion_note']}")
    a("")
    a("| Quantity | Value |")
    a("|---|---|")
    for k in ("S0", "u", "d", "r"):
        a(f"| {k} | {fmt(base_in[k], 'g')} |")
    a(f"| R = 1 + r | {fmt(derived['R'], 'g')} |")
    a(f"| Su = S0·u | {fmt(derived['Su'], 'g')} |")
    a(f"| Sd = S0·d | {fmt(derived['Sd'], 'g')} |")
    a(f"| Strike K | {fmt(examples['call']['claim']['K'], 'g')} |")
    a(f"| Digital cash payout | {fmt(examples['digital']['claim']['cash_payout'], 'g')} (paid if S_T > K, strict) |")
    a(f"| Market status | {examples['call']['classification']['status']} |")
    a(f"| Risk-neutral q = (R − d)/(u − d) | {fmt(q, '.10g')} |")
    a("")
    a("Tolerances used (units in `docs/methodology.md`): "
      + ", ".join(f"`{k}` = {v:g}" for k, v in meta["tolerances"].items()) + ".")
    a("")
    a("## 3. Baseline pricing")
    a("")
    a("| Claim | Payoff up | Payoff down | Arbitrage-free price | Replication Δ (shares) | Replication B (time-0 cash) | Replication cost | Price − cost |")
    a("|---|---|---|---|---|---|---|---|")
    for t, name in (("call", "European call"), ("put", "European put"), ("digital", "Cash-or-nothing digital call")):
        e = examples[t]
        a(f"| {name} | {fmt(e['terminal_payoffs']['up'], 'g')} | {fmt(e['terminal_payoffs']['down'], 'g')} | "
          f"{fmt(e['pricing']['arbitrage_free_price'], '.10f')} | {fmt(e['replication']['delta'], '.10g')} | "
          f"{fmt(e['replication']['cash_B'], '.10g')} | {fmt(e['replication']['initial_cost'], '.10f')} | "
          f"{fmt(e.get('price_minus_replication_cost'), '.3e')} |")
    a("")
    a(f"State prices: π_up = {fmt(sp['pi_up'], '.10g')}, π_down = {fmt(sp['pi_down'], '.10g')}; "
      f"π_up + π_down − 1/R = {fmt(sp['pi_up_plus_pi_down_minus_1_over_R'], '.3e')}; "
      f"π_up·Su + π_down·Sd − S0 = {fmt(sp['pi_up_Su_plus_pi_down_Sd_minus_S0'], '.3e')}. "
      "State prices are time-0 prices of one unit paid in a state; they sum to 1/R and are not probabilities.")
    a("")
    c_price = examples["call"]["pricing"]["arbitrage_free_price"]
    p_price = examples["put"]["pricing"]["arbitrage_free_price"]
    parity = c_price - p_price - (float(base_in["S0"]) - float(examples["call"]["claim"]["K"]) / derived["R"])
    a(f"Put–call parity check: C − P − (S0 − K/R) = {fmt(parity, '.3e')}.")
    a("")
    a("## 4. Replication checks")
    a("")
    a("Each claim is replicated independently (the put does not reuse call results). Portfolio terminal values are "
      "recomputed from Δ and B, and `numpy.linalg.solve` provides a second solution of the 2×2 system.")
    a("")
    cols = ["scenario_id", "claim", "market_status", "delta", "cash_B", "initial_cost", "error_up", "error_down",
            "max_abs_error", "linalg_max_abs_diff", "check_passed"]
    a(_md_table(rep[cols], {"delta": ".6g", "cash_B": ".6g", "initial_cost": ".6f", "error_up": ".2e",
                            "error_down": ".2e", "max_abs_error": ".2e", "linalg_max_abs_diff": ".2e"}))
    a("")
    a("For markets that are not arbitrage-free, the `initial_cost` column is an algebraic replication cost, "
      "**not** an arbitrage-free valuation.")
    a("")
    a("## 5. Scenario results")
    a("")
    cols = ["scenario_id", "market_status", "exact_boundary", "q_candidate", "claim", "arbitrage_free_price",
            "algebraic_replication_cost_not_arbitrage_free", "warnings", "error_message"]
    sm = summary[cols].rename(columns={"algebraic_replication_cost_not_arbitrage_free": "algebraic_cost_NOT_arbitrage_free"})
    a(_md_table(sm, {"q_candidate": ".6g", "arbitrage_free_price": ".6f", "algebraic_cost_NOT_arbitrage_free": ".6f"}))
    a("")
    a("`q_candidate` is reported without clipping. It is a risk-neutral probability only for `arbitrage_free` rows.")
    a("")
    a("## 6. Arbitrage scenarios")
    a("")
    a("### 6.1 Stock/cash (underlying-market) arbitrage")
    a("")
    ua = und[und["case"].notna() & (und["case"] != "")]
    cols = ["scenario_id", "market_status", "case", "stock_shares", "cash_account", "initial_cost", "payoff_up",
            "payoff_down", "nonnegative_payoffs", "strict_gain_in_some_state", "verified"]
    a(_md_table(ua[cols], {"stock_shares": "g", "cash_account": "g", "initial_cost": ".3g", "payoff_up": ".6g", "payoff_down": ".6g"}))
    a("")
    unresolved_verified = ua[(ua["market_status"] == "near_boundary_unresolved") & (ua["verified"])]
    a("Case A (R ≤ d): buy 1 share, borrow S0. Case B (R ≥ u): short 1 share, deposit S0. Payoffs are computed in exact "
      "rational arithmetic, so the equality cases R = d and R = u show an exact zero in one state and a strict gain in the other.")
    if len(unresolved_verified):
        ids = ", ".join(f"`{s}`" for s in unresolved_verified["scenario_id"])
        a("")
        a(f"Note: {ids} keeps the status `near_boundary_unresolved` because R is within the stated relative tolerance of "
          "a boundary. Taking its decimal inputs as exact, the candidate portfolio's payoffs are still nonnegative with a "
          "strict gain, so the portfolio check passes; the *classification* is nevertheless not reported as a confident "
          "arbitrage, because it rests on digits far beyond realistic input precision.")
    a("")
    a("### 6.2 Quote arbitrage")
    a("")
    cols = ["scenario_id", "direction", "row_type", "leg", "quantity", "time0_cashflow", "payoff_up", "payoff_down", "verified"]
    a(_md_table(quotes[cols], {"quantity": ".6g", "time0_cashflow": ".6g", "payoff_up": ".6g", "payoff_down": ".6g"}))
    a("")
    a("`time0_cashflow` is cash received at time 0 (negative = paid); the NET row's time-0 cash flow equals minus the "
      "initial cost. A verified quote arbitrage has zero initial cost and terminal profit |M − V|·R in both states. "
      "These are frictionless-model results, not evidence that any real quote is executable.")
    a("")
    a("## 7. Sensitivity results")
    a("")
    s_af = strike["call_arbitrage_free_price"]
    a(f"**Strike sweep** ({len(strike)} strikes from {fmt(strike['strike'].min(), 'g')} to {fmt(strike['strike'].max(), 'g')}): "
      f"call price falls from {fmt(s_af.iloc[0], '.6f')} to {fmt(s_af.iloc[-1], '.6f')}; put price rises from "
      f"{fmt(strike['put_arbitrage_free_price'].iloc[0], '.6f')} to {fmt(strike['put_arbitrage_free_price'].iloc[-1], '.6f')}. "
      f"Call price nonincreasing in K: {'yes' if (s_af.diff().dropna() <= 1e-12).all() else 'no'}; put price nondecreasing: "
      f"{'yes' if (strike['put_arbitrage_free_price'].diff().dropna() >= -1e-12).all() else 'no'}. "
      f"Maximum |put–call parity residual|: {fmt(strike['put_call_parity_residual'].abs().max(), '.3e')}. "
      f"The call replication hedge ratio ranges from {fmt(strike['call_replication_hedge_ratio'].min(), 'g')} to "
      f"{fmt(strike['call_replication_hedge_ratio'].max(), 'g')}, changing only for Sd < K < Su.")
    a("")
    af = rate[rate["market_status"] == "arbitrage_free"]
    a(f"**Rate sweep** ({len(rate)} values of r from {fmt(rate['r'].min(), 'g')} to {fmt(rate['r'].max(), 'g')}): "
      f"arbitrage-free prices exist for {len(af)} points, r from {fmt(af['r'].min(), 'g')} to {fmt(af['r'].max(), 'g')}. "
      f"Over that range the call price rises from {fmt(af['call_arbitrage_free_price'].iloc[0], '.6f')} to "
      f"{fmt(af['call_arbitrage_free_price'].iloc[-1], '.6f')} and the put price falls from "
      f"{fmt(af['put_arbitrage_free_price'].iloc[0], '.6f')} to {fmt(af['put_arbitrage_free_price'].iloc[-1], '.6f')}. "
      "Status counts: " + ", ".join(f"{k}: {v}" for k, v in rate["market_status"].value_counts().sort_index().items()) + ". "
      "Rows outside the arbitrage-free region have empty price cells.")
    a("")
    gp = grid["call_arbitrage_free_price"]
    a(f"**(u, d) grid** ({len(grid)} points, u {fmt(grid['u'].min(), 'g')}–{fmt(grid['u'].max(), 'g')}, "
      f"d {fmt(grid['d'].min(), 'g')}–{fmt(grid['d'].max(), 'g')}, r fixed at baseline): "
      + ", ".join(f"{k}: {v}" for k, v in grid["market_status"].value_counts().sort_index().items())
      + f". Call prices on the arbitrage-free cells range from {fmt(gp.min(), '.6f')} to {fmt(gp.max(), '.6f')}.")
    a("")
    a("## 8. Figures")
    a("")
    captions = {
        "one_period_tree.png": "One-period stock tree with q, 1 − q and claim payoffs.",
        "replication_payoffs.png": "Claim payoffs versus replicating-portfolio payoffs in each state.",
        "call_put_vs_strike.png": "Call and put arbitrage-free price versus strike.",
        "hedge_ratio_vs_strike.png": "Replication hedge ratio (exact payoff-matching Δ) versus strike.",
        "price_vs_rate.png": "Prices versus the effective one-period rate; arbitrage regions shaded with no prices shown.",
        "arbitrage_regions.png": "Market classification over (d, u); invalid u ≤ d cells masked.",
        "call_price_heatmap.png": "Call price over the arbitrage-free (d, u) region; all other cells masked.",
    }
    for name in FIGURE_FILES:
        if (results_dir / "figures" / name).is_file():
            a(f"![{captions[name]}](figures/{name})")
            a("")
            a(f"*{captions[name]}*")
            a("")
    a("## 9. Limitations")
    a("")
    a("- One period and two states only; no multi-period trees, American exercise, GBM, Black–Scholes, Monte Carlo or implied volatility.")
    a("- Frictionless assumptions: no transaction costs, no bid–ask spreads, unrestricted short selling, equal borrowing and lending rate, fractional positions, no dividends.")
    a("- Both terminal states are assumed possible; the parameters are illustrative, not calibrated to market data.")
    a("- The replication hedge ratio is an exact one-period payoff-matching coefficient, not a spot-price derivative; no gamma is computed.")
    a("- Quote-arbitrage results are model statements and do not show that a real quote is executable.")
    a("- Near-boundary classification depends on the stated tolerance; inputs are interpreted as exact decimals.")
    a("")
    return "\n".join(L)


def write_report(results_dir: Path) -> Path:
    """Build and write ``research_report.md`` in ``results_dir``."""
    results_dir = Path(results_dir)
    return write_text(results_dir / "research_report.md", build_report(results_dir))


def _package_version() -> str:
    try:
        return importlib_metadata.version("binomial-arbitrage")
    except importlib_metadata.PackageNotFoundError:
        from . import __version__

        return __version__
