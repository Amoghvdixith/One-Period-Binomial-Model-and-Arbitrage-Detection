"""Price a call, put or cash-or-nothing digital call in the one-period model.

Examples (run from the project root):

    python scripts/price_claim.py --config configs/baseline.json --claim call
    python scripts/price_claim.py --config configs/baseline.json --claim digital --output out.json

Prints a JSON record. In an arbitrage-containing market no arbitrage-free
price is reported; the algebraic replication cost appears in a separately
labelled field.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from binomial_arbitrage import Tolerances, ValidationError
from binomial_arbitrage.payoffs import ClaimSpec
from binomial_arbitrage.reporting import _sanitize, claim_record, load_json, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Price one claim in a one-period binomial market (R = 1 + r, effective simple one-period rate).",
    )
    parser.add_argument("--config", type=Path, required=True, help="Market config JSON with S0, u, d, r, K and optional cash_payout.")
    parser.add_argument("--claim", choices=("call", "put", "digital"), required=True, help="Claim to price.")
    parser.add_argument("--strike", type=str, default=None, help="Override the strike K from the config.")
    parser.add_argument("--cash-payout", type=str, default=None, help="Override the digital cash payout.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write the JSON record (overwritten).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_json(args.config)
        for key in ("S0", "u", "d", "r", "K"):
            if key not in cfg:
                raise ValidationError(f"config is missing required key '{key}'")
        mapping = {"type": args.claim, "K": args.strike if args.strike is not None else cfg["K"]}
        if args.claim == "digital":
            mapping["cash_payout"] = args.cash_payout if args.cash_payout is not None else cfg.get("cash_payout", 1)
        spec = ClaimSpec.from_mapping(mapping)
        record = claim_record(cfg, spec, Tolerances())
    except (ValidationError, FileNotFoundError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(_sanitize(record), indent=2, ensure_ascii=False))
    if args.output is not None:
        write_json(args.output, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
