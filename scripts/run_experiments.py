"""Run all scenarios and sensitivity analyses; write CSV, JSON and PNG outputs.

Example (run from the project root):

    python scripts/run_experiments.py --config configs/scenarios.json

Outputs are written to ``results/baseline`` by default and are overwritten
deterministically on every run (no appending).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from _bootstrap import PROJECT_ROOT

from binomial_arbitrage import ValidationError
from binomial_arbitrage.reporting import run_experiments


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the one-period binomial scenario set and sensitivity sweeps (R = 1 + r).",
    )
    parser.add_argument("--config", type=Path, required=True, help="Scenario config JSON (references the baseline config).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "baseline",
        help="Directory for results (default: results/baseline under the project root).",
    )
    parser.add_argument("--no-figures", action="store_true", help="Skip chart generation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        meta = run_experiments(args.config, args.output_dir, make_figures=not args.no_figures)
    except (ValidationError, FileNotFoundError, KeyError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    counts = meta["counts"]
    print(f"Scenarios: {counts['scenarios']} ({counts['rejected_invalid_input']} rejected as invalid input, as expected)")
    print(f"Scenarios by status: {counts['scenarios_by_status']}")
    print(f"Replication checks passed: {counts['replication_checks_passed']}/{counts['replication_checks']}")
    print(f"Max abs replication error: {meta['max_abs_replication_error']:.3e}")
    print(
        "Verified stock/cash arbitrage portfolios: "
        f"{counts['underlying_arbitrage_verified_in_arbitrage_markets']}/{counts['arbitrage_markets']} arbitrage markets "
        f"(+{counts['underlying_candidates_verified_in_unresolved_markets']} candidate in a near-boundary unresolved market)"
    )
    print(f"Verified quote arbitrage portfolios: {counts['quote_arbitrage_verified']}/{counts['quote_scenarios']} quote scenarios")
    print(f"Warnings: {len(meta['warnings'])}; failures: {len(meta['failures'])}")
    for f in meta["failures"]:
        print(f"  FAILURE: {f}")
    print(f"Outputs written: {len(meta['outputs'])} files")
    return 1 if meta["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
