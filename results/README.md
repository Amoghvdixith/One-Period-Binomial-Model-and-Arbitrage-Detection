# Results

Every file in `baseline/` is produced by actually running the project's code. Nothing is typed in by hand. Re-running the commands below overwrites the files deterministically. Only the timestamp in `run_metadata.json` and the date in the report header change between identical runs.

## Generation commands (run from the project root)

```bash
python scripts/run_experiments.py --config configs/scenarios.json
```

```bash
python -m pytest -q --junitxml=results/baseline/test_results.xml
```

```bash
python scripts/generate_report.py --results-dir results/baseline
```

Run the report last, so that it picks up the test counts from `test_results.xml`.

## Units

- **Currency units:** prices, payoffs, the cash amount `B`, costs, errors and profits. The model has no currency.
- **Shares:** `Δ`, the replication hedge ratio.
- **Dimensionless:** `u`, `d`, `R` and `q`.
- **Effective simple rate:** `r`, measured per single model period (`R = 1 + r`).

## Output definitions

| File | Contents |
|---|---|
| `example_call.json`, `example_put.json`, `example_digital.json` | Full baseline analysis of one claim: inputs, classification, payoffs, price, state prices, replication with independent checks, and the stock/cash arbitrage block. |
| `scenario_summary.csv` | One row per scenario: status, exact-boundary flag, unclipped `q_candidate`, payoffs, `arbitrage_free_price` (empty unless the market is arbitrage-free), `algebraic_replication_cost_not_arbitrage_free`, Δ, B, maximum replication error, arbitrage and quote verification flags, warnings, and rejection messages. |
| `replication_checks.csv` | For each scenario with valid inputs: Δ, B, initial cost, terminal portfolio values, signed errors, maximum absolute error, the `numpy.linalg.solve` cross-check, condition number, pass flag, and price minus replication cost. |
| `underlying_arbitrage.csv` | Stock/cash arbitrage positions (`stock_shares`; `cash_account`, the signed time-0 cash, where negative means borrowing), initial cost, payoffs, and the three verification flags. |
| `quote_arbitrage.csv` | Every leg of each quote-arbitrage portfolio (quantity, time-0 cash received, up and down payoffs) plus a NET row with verification. |
| `strike_sensitivity.csv` | Call and put prices, replication hedge ratios, cash positions and the put–call parity residual for K = 70…130. |
| `rate_sensitivity.csv` | Status, `q_candidate`, call, put and digital prices (empty outside the arbitrage-free region) and hedge ratios for r = −0.15…0.20. |
| `up_down_grid.csv` | Status, validity, `q_candidate`, call price (arbitrage-free cells only) and hedge ratio for each (u, d) grid point. |
| `run_metadata.json` | Configurations, rate convention, tolerances, Python and dependency versions, UTC timestamp, counts, warnings, failures and SHA-256 checksums of the config files. It contains no absolute paths. |
| `test_results.xml` | JUnit XML from the final pytest run. |
| `research_report.md` | Report generated only from the files above. |
| `figures/*.png` | The seven static charts listed in the report. |

## Execution status

The latest run used Python 3.14.4 with numpy 2.5.4, pandas 3.1.1, matplotlib 3.11.2 and pytest 9.2.0:

- **Scenarios:** 25 evaluated; 2 invalid-input scenarios were rejected deliberately.
- **Replication checks:** 23 of 23 passed.
- **Run warnings and failures:** 3 run warnings (two near-boundary, one narrow-separation), 0 run failures.
- **Tests:** 222 collected, 222 passed, 0 failed, 0 skipped (see `test_results.xml`).
