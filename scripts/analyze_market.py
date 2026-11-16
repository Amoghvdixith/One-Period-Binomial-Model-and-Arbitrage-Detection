"""Classify a one-period market and summarise prices, state prices and arbitrage.

Example (run from the project root):

    python scripts/analyze_market.py --config configs/baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from binomial_arbitrage import Tolerances, ValidationError
from binomial_arbitrage.reporting import _sanitize, load_json, market_record, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Classify a one-period stock/cash market (d < R < u test with R = 1 + r) and report state prices, "
            "the explicit stock/cash arbitrage portfolio if any, and call/put/digital valuations."
        ),
    )
    parser.add_argument("--config", type=Path, required=True, help="Market config JSON with S0, u, d, r, K.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write the JSON record (overwritten).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_json(args.config)
        for key in ("S0", "u", "d", "r", "K"):
            if key not in cfg:
                raise ValidationError(f"config is missing required key '{key}'")
        record = market_record(cfg, Tolerances())
    except (ValidationError, FileNotFoundError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(_sanitize(record), indent=2, ensure_ascii=False))
    if args.output is not None:
        write_json(args.output, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
