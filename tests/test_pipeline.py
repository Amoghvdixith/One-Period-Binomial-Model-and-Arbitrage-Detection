"""End-to-end pipeline tests. All outputs go to pytest's tmp_path."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from conftest import EXPECTED, PROJECT_ROOT
from binomial_arbitrage.reporting import FIGURE_FILES, OUTPUT_FILES, run_experiments

CONFIG = PROJECT_ROOT / "configs" / "scenarios.json"


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("results")
    meta = run_experiments(CONFIG, out, make_figures=True)
    assert meta["failures"] == []
    return out


def test_all_outputs_written(run_dir):
    for name in OUTPUT_FILES:
        assert (run_dir / name).is_file(), name
    for name in FIGURE_FILES:
        path = run_dir / "figures" / name
        assert path.is_file() and path.stat().st_size > 10_000, name
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_scenario_summary_schema_and_counts(run_dir):
    df = pd.read_csv(run_dir / "scenario_summary.csv")
    required = {
        "scenario_id", "market_status", "q_candidate", "payoff_up", "payoff_down", "arbitrage_free_price",
        "algebraic_replication_cost_not_arbitrage_free", "replication_hedge_ratio", "replication_cash_B",
        "max_abs_replication_error", "underlying_arbitrage_case", "underlying_arbitrage_verified",
        "quote_direction", "quote_arbitrage_verified", "warnings", "error_message",
    }
    assert required <= set(df.columns)
    assert df["scenario_id"].is_unique
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert len(df) == len(cfg["scenarios"])
    s = df.set_index("scenario_id")
    assert s.loc["baseline_call", "arbitrage_free_price"] == pytest.approx(float(EXPECTED["call_price"]), abs=1e-12)
    assert s.loc["baseline_put", "arbitrage_free_price"] == pytest.approx(float(EXPECTED["put_price"]), abs=1e-12)
    for sid in ("r_below_d", "r_above_u", "r_equal_d_exact", "r_equal_u_exact"):
        assert pd.isna(s.loc[sid, "arbitrage_free_price"])
        assert bool(s.loc[sid, "underlying_arbitrage_verified"])
    assert s.loc["degenerate_u_equals_d", "market_status"] == "invalid_input"
    assert s.loc["near_boundary_inside", "market_status"] == "near_boundary_unresolved"


def test_quote_and_replication_tables(run_dir):
    q = pd.read_csv(run_dir / "quote_arbitrage.csv")
    assert {"scenario_id", "row_type", "leg", "quantity", "time0_cashflow", "payoff_up", "payoff_down", "verified"} <= set(q.columns)
    nets = q[q["row_type"] == "net"].set_index("scenario_id")
    assert nets.loc["quote_overpriced_call", "direction"] == "overpriced"
    assert nets.loc["quote_underpriced_call", "direction"] == "underpriced"
    assert nets.loc["quote_matching_call", "direction"] == "within_tolerance"
    assert nets.loc["quote_in_arbitrage_market", "direction"] == "not_assessed"
    rep = pd.read_csv(run_dir / "replication_checks.csv")
    assert rep["check_passed"].all()
    assert rep["max_abs_error"].max() < 1e-9


def test_metadata_has_no_absolute_paths(run_dir):
    text = (run_dir / "run_metadata.json").read_text(encoding="utf-8")
    meta = json.loads(text)
    for key in ("model_convention", "tolerances", "python_version", "dependency_versions",
                "execution_timestamp_utc", "counts", "warnings", "failures", "config_files"):
        assert key in meta
    assert str(PROJECT_ROOT) not in text
    assert str(Path.home()) not in text
    assert str(run_dir) not in text
    assert all(len(v["sha256"]) == 64 for v in meta["config_files"].values())


def test_repeated_runs_do_not_duplicate(tmp_path):
    out = tmp_path / "rerun"
    run_experiments(CONFIG, out, make_figures=False)
    first = {n: (out / n).read_bytes() for n in OUTPUT_FILES if n.endswith(".csv") or n.startswith("example_")}
    run_experiments(CONFIG, out, make_figures=False)
    for name, content in first.items():
        assert (out / name).read_bytes() == content, f"{name} changed between identical runs"
    assert sorted(p.name for p in out.iterdir() if p.suffix == ".tmp") == []


def test_report_values_agree_with_saved_results(run_dir):
    import re

    from binomial_arbitrage.reporting import build_report, fmt, write_report

    write_report(run_dir)
    text = (run_dir / "research_report.md").read_text(encoding="utf-8")
    assert text == build_report(run_dir)  # report is a pure function of saved files
    call = json.loads((run_dir / "example_call.json").read_text(encoding="utf-8"))
    put = json.loads((run_dir / "example_put.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert fmt(call["pricing"]["arbitrage_free_price"], ".10f") in text
    assert fmt(put["pricing"]["arbitrage_free_price"], ".10f") in text
    assert fmt(meta["max_abs_replication_error"], ".3e") in text
    assert f"**{meta['counts']['scenarios']}**" in text
    summary = pd.read_csv(run_dir / "scenario_summary.csv")
    for sid in summary["scenario_id"]:
        assert f"| {sid} |" in text
    for section in ("## 1. Overview", "## 2. Model configuration", "## 3. Baseline pricing", "## 4. Replication checks",
                    "## 6. Arbitrage scenarios", "## 7. Sensitivity results", "## 8. Figures", "## 9. Limitations"):
        assert section in text
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert len(links) == len(FIGURE_FILES)
    for link in links:
        assert (run_dir / link).is_file(), link


def test_generate_report_script(tmp_path):
    out = tmp_path / "res"
    run_experiments(CONFIG, out, make_figures=False)
    proc = subprocess.run(
        [sys.executable, "scripts/generate_report.py", "--results-dir", str(out)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "research_report.md").is_file()
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run(
        [sys.executable, "scripts/generate_report.py", "--results-dir", str(empty)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 2 and "run_experiments.py first" in proc.stderr


def test_example_json_matches_targets(run_dir):
    call = json.loads((run_dir / "example_call.json").read_text(encoding="utf-8"))
    assert call["pricing"]["arbitrage_free_price"] == pytest.approx(float(EXPECTED["call_price"]), abs=1e-12)
    assert call["replication"]["delta"] == pytest.approx(0.6, abs=1e-12)
    assert call["replication_check_passed"] is True


@pytest.mark.parametrize("claim", ["call", "put", "digital"])
def test_price_claim_script(claim, tmp_path):
    out = tmp_path / f"{claim}.json"
    proc = subprocess.run(
        [sys.executable, "scripts/price_claim.py", "--config", "configs/baseline.json", "--claim", claim, "--output", str(out)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["claim"]["type"] == claim
    assert out.is_file()


def test_analyze_market_script():
    proc = subprocess.run(
        [sys.executable, "scripts/analyze_market.py", "--config", "configs/baseline.json"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    rec = json.loads(proc.stdout)
    assert rec["classification"]["status"] == "arbitrage_free"
    assert abs(rec["put_call_parity"]["residual"]) < 1e-12


def test_scripts_report_clear_input_errors(tmp_path):
    bad = tmp_path / "bad config.json"  # path with a space
    bad.write_text(json.dumps({"S0": 100, "u": 1.05, "d": 1.05, "r": 0.02, "K": 100}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "scripts/price_claim.py", "--config", str(bad), "--claim", "call"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    # A degenerate market is reported as invalid input inside the JSON record (not a crash).
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["classification"]["status"] == "invalid_input"
    missing = subprocess.run(
        [sys.executable, "scripts/price_claim.py", "--config", str(tmp_path / "nope.json"), "--claim", "call"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert missing.returncode == 2 and "Input error" in missing.stderr


def test_run_experiments_script_with_spaces_in_output_dir(tmp_path):
    out = tmp_path / "out dir with spaces"
    proc = subprocess.run(
        [sys.executable, "scripts/run_experiments.py", "--config", "configs/scenarios.json", "--output-dir", str(out), "--no-figures"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "scenario_summary.csv").is_file()
