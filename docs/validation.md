# Validation

## Test results

The figures below come from the final test run, saved to `results/baseline/test_results.xml` with:

```bash
python -m pytest -q --junitxml=results/baseline/test_results.xml
```

| Collected | Passed | Failed | Errors | Skipped |
|---|---|---|---|---|
| 222 | 222 | 0 | 0 | 0 |

Collected test cases per file. Parametrised tests count once per parameter set, which is why some files have many more cases than test functions.

| File | Test cases | Covers |
|---|---|---|
| `test_validation.py` | 45 | finite inputs, `S0 ≤ 0`, invalid multipliers, `u = d`, `r ≤ −1`, negative strike, negative payout, conditioning warnings and rejection, exact classification statuses, unclipped `q` |
| `test_payoffs.py` | 10 | call and put in and out of the money, strike equality, zero strike, digital strict inequality, generic negative payoffs |
| `test_pricing.py` | 114 | baseline exact targets, risk-neutral price vs replication cost (6 markets × 4 claims), state-price identities, put–call parity (6 markets × 7 strikes), call and put bounds, negative rates, refusal to label arbitrage-market values as arbitrage-free |
| `test_replication.py` | 11 | hand-calculated Δ and B for call and put, both states matched, generic claims, exact `Fraction` cross-check, `numpy.linalg.solve` cross-check |
| `test_arbitrage.py` | 20 | `R < d`, `R > u`, `R = d`, `R = u`, zero cost, nonnegative payoffs, strict gain, near-boundary cases, overpriced and underpriced quotes, exact quote agreement, quote not assessed in an arbitrage market |
| `test_sensitivity.py` | 8 | exact Decimal ranges, output shape, call nonincreasing and put nondecreasing in K, prices only where permitted, invalid-region masking |
| `test_pipeline.py` | 14 | end-to-end run, output schemas, report values match saved results, image links resolve, repeated runs give identical CSV and JSON files, scripts (including paths containing spaces and clear input errors), no absolute paths in metadata |

No coverage tool was run, so no coverage percentage is claimed.

pytest records the machine's hostname in its JUnit XML. A hook in `tests/conftest.py` replaces it with `redacted` after the file is written, so the saved results contain no personal identifier. The counts and outcomes are not changed.

## Independent checks

The tests are designed not to just repeat the implementation's formulas:

- **Hand-derived baseline targets** are written as exact fractions in `tests/conftest.py`: `R = 102/100`, `q = 1/2`, `C = 6/1.02`, `P = 4/1.02`, `Δ_call = 0.6`, `B_call = −11.04/0.204`, `Δ_put = −0.4`, `B_put = 8.96/0.204`, digital = `0.5/1.02`.
- **Exact rational replication** for an awkward market (`S0 = 73.3, u = 1.13, d = 0.87, r = 0.017`, payoffs `−31/7` and `19/3`) is computed with `fractions.Fraction` directly in the test.
- **Independent linear solve:** the 2×2 replication system is also solved with `numpy.linalg.solve`.
- **Model-free identities** are tested across several markets and strikes: put–call parity (`C − P = S0 − K/R`), and the no-arbitrage bounds `max(S0 − K/R, 0) ≤ C ≤ S0` and `max(K/R − S0, 0) ≤ P ≤ K/R`.
- **Closed forms that need no pricing code:** deep in-the-money call `= S0 − K/R`, zero-strike call `= S0`, high-strike put `= K/R − S0`, and the negative-rate `q = 7/15`.
- **Arbitrage payoffs computed by hand**, for example `100·(1.25 − 1.02) = 23` and `100·(1.10 − 0.98) = 12`.
- **Exact boundary fixtures** given as Decimal strings (e.g. `d = "1.02", r = "0.02"`), so that `R = d` holds exactly rather than approximately.

## Tolerances used in tests

| Check | Tolerance |
|---|---|
| Baseline targets | absolute and relative 1e-12 |
| Risk-neutral price vs replication cost | relative 1e-10, absolute 1e-10·(1 + \|Xu\| + \|Xd\|) |
| State-price identities | relative 1e-13 to 1e-14 |
| Put–call parity | relative 1e-12, absolute 1e-10 |
| Arbitrage zero cost | absolute 1e-12 (underlying), 1e-10 (quote) |
| Replication errors in the pipeline | maximum below 1e-9 |

The model's own tolerance policy is documented in `methodology.md` §10.

## Validation limitations

- The tests confirm internal consistency and agreement with hand-derived values. They don't validate the model against market data, because the project uses none.
- Floating-point results are checked to stated tolerances, not bit for bit, except where exact arithmetic is used.
- Chart content was reviewed visually during development. The automated tests only check that each PNG exists, is non-trivial in size and has a valid PNG header.
- The test suite was run on one platform (Windows, Python 3.14.4, with the library versions in `requirements-lock.txt`). Other platforms and versions were not tested.
