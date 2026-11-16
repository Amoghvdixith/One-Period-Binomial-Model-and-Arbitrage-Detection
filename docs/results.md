# Results

All values on this page are copied from the files in `results/baseline/`, which were produced by `python scripts/run_experiments.py --config configs/scenarios.json`. The generated `results/baseline/research_report.md` contains the complete tables. If you re-run the experiment, check the numbers against the regenerated files.

## Baseline outputs

Market: `S0 = 100, u = 1.12, d = 0.92, r = 0.02` (so `R = 1.02`), with `K = 100`. Status: `arbitrage_free`, `q = 0.5`.

| Claim | Payoffs (up, down) | Arbitrage-free price | Replication Δ | Replication B (time 0) |
|---|---|---|---|---|
| European call | (12, 0) | 5.8823529412 | 0.6 | −54.11764706 |
| European put | (0, 8) | 3.9215686275 | −0.4 | 43.92156863 |
| Digital call (payout 1, S_T > K) | (1, 0) | 0.4901960784 | 0.05 | −4.509803922 |

- **State prices:** `π_up = π_down = 0.4901960784`. The identity residuals (`π_up + π_down − 1/R` and `π_up·Su + π_down·Sd − S0`) were both 0.000e+00.
- **Put–call parity:** the residual is −7.550e-15.
- **Comparison with the guide:** these values match the independently specified targets (`6/1.02`, `0.6`, `4/1.02`). The guide's stated call price of about 8.43 is not reproduced (see `reference_corrections.md`).

## Scenario findings (25 scenarios)

Status counts: 16 `arbitrage_free`, 2 `arbitrage_R_le_d`, 3 `arbitrage_R_ge_u`, 2 `near_boundary_unresolved` and 2 `invalid_input`. The two invalid-input scenarios were rejected deliberately: `u = d` is degenerate, and a separation of `(u−d)/u ≈ 9.8e-14` is ill-conditioned.

- **Deep in-the-money call (K = 80):** 21.568627, exactly `100 − 80/1.02`.
- **Deep out-of-the-money call (K = 130):** 0.
- **Zero-strike call:** 100 (= S0).
- **Negative rate, no arbitrage** (`u = 1.05, d = 0.90, r = −0.03`): `q = 0.466667`, call = 2.405498.
- **Both multipliers above 1** (`u = 1.15, d = 1.01, r = 0.05`): `q = 0.285714`, call (K = 105) = 2.721088.
- **Both multipliers below 1** (`u = 0.99, d = 0.85, r = −0.05`): `q = 0.714286`, call (K = 90) = 6.766917.
- **Generic claim** `(−5, 10)`: price 2.450980, with Δ = −0.75.
- **Arbitrage markets:** no arbitrage-free price was produced for any of them. Their algebraic replication costs appear in a separately labelled column, and `q_candidate` values such as −0.15, 0, 1 and 1.714286 are reported unclipped.
- **Narrow separations:** a narrow but well-conditioned separation (`u − d = 0.0002`) priced normally. A separation of `u − d = 1e-6` priced but raised the `narrow_state_separation` warning.

## Replication errors

23 replication checks were run (every scenario with valid inputs), and **23 passed**. The maximum absolute replication error was **1.599e-14** currency units. The largest gap between the closed-form solution and the independent `numpy.linalg.solve` solution was 3.06e-09, in the `narrow_separation_warning` scenario. That gap reflects the conditioning of the float linear solve when `u − d = 1e-6`; the exact-arithmetic replication itself matched both payoffs to 1.7e-15.

## Arbitrage verification

- **Stock/cash portfolios:** 5 arbitrage markets, and all 5 were verified (zero cost, exactly nonnegative payoffs, strict gain):
  - `r_below_d`: payoffs (23, 3)
  - `r_above_u`: payoffs (5, 12)
  - `r_equal_d_exact`: payoffs (10, 0)
  - `r_equal_u_exact`: payoffs (0, 20)
  - `quote_in_arbitrage_market`: payoffs (5, 12)
- **Near-boundary candidate:** the `near_boundary_outside` market (R below d by 1e-12) keeps status `near_boundary_unresolved`. Its candidate portfolio's exact payoffs (10, 1e-10) pass the checks, and the report states this separately. The `near_boundary_inside` market has no stock/cash arbitrage candidate.
- **Quote arbitrage:**
  - Overpriced call (M = 6.50): verified, profit 0.63 in each state.
  - Underpriced call (M = 5.20): verified, profit 0.696 in each state.
  - Overpriced put (M = 4.50): verified, profit 0.59 in each state.
  - Matching call quote: within tolerance, no discrepancy detected.
  - Quote in an arbitrage market: not assessed, because the underlying diagnosis takes precedence.

## Sensitivity findings

- **Strike sweep** (61 strikes, 70–130): the call price falls from 31.372549 to 0 and the put price rises from 0 to 27.450980. The call price is nonincreasing and the put price nondecreasing in K. The maximum put–call parity residual is 8.882e-15. The call replication hedge ratio is 1 for K ≤ Sd = 92, 0 for K ≥ Su = 112, and linear in between.
- **Rate sweep** (71 values of r, −0.15 to 0.20): prices exist only for the 39 arbitrage-free points, r from −0.075 to 0.115. Over that range the call price rises from 0.324324 to 10.493274 and the put price falls from 8.432432 to 0.179372. The boundary points r = −0.08 (R = d) and r = 0.12 (R = u) are classified as arbitrage.
- **(u, d) grid** (3,721 points):
  - 1,596 arbitrage-free
  - 551 `R ≤ d`
  - 713 `R ≥ u`
  - 861 invalid (`u ≤ d`)

  Call prices on the arbitrage-free cells range from 1.960784 to 20.588235.

## Numerical caveats

- **Inputs are treated as exact decimals.** For example, `0.02` means two hundredths, not the nearest binary double. Changing this interpretation could change exact-boundary results.
- **The near-boundary threshold (1e-10 relative) is a policy choice.** Markets within it are reported as unresolved, not priced.
- **Errors are reported, not hidden.** Replication errors around 1e-14 are floating-point rounding. They are reported rather than suppressed.
- **Charts show cells, not lines.** The grid has a step of 0.01, so the boundary lines in the charts fall on cell centres, and exact-boundary cells (d = 1.02 or u = 1.02) appear as arbitrage cells.
