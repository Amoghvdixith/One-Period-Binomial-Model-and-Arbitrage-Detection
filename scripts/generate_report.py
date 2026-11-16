"""Generate ``research_report.md`` from saved experiment results.

Example (run from the project root, after run_experiments.py):

    python scripts/generate_report.py --results-dir results/baseline

The report reads only the saved CSV/JSON files (and test_results.xml if
present); it does not recompute or hard-code findings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from binomial_arbitrage.reporting import write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the Markdown research report from saved results.")
    parser.add_argument("--results-dir", type=Path, required=True, help="Folder containing the experiment outputs.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.results_dir / "run_metadata.json").is_file():
        print(
            f"Input error: {args.results_dir} has no run_metadata.json; run scripts/run_experiments.py first.",
            file=sys.stderr,
        )
        return 2
    try:
        path = write_report(args.results_dir)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Input error: incomplete results in {args.results_dir}: {exc}", file=sys.stderr)
        return 2
    print(f"Report written: {path.name} in {args.results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
