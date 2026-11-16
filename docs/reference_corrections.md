# Reference corrections (Project 1 of the guide)

The scope reference is Project 1, *One-Period Binomial Model and Arbitrage Detection*, in the PDF guide *Basic Quantitative Finance Projects: A Practical Guide for Aspiring Quants*, which the project owner supplied. I inspected the PDF locally. It is not copied, redistributed or quoted at length here. This file records the material discrepancies I found in Project 1, and what this project does instead. No other project from the guide is implemented.

## 1. Inconsistent interest-rate convention

The guide's mathematical text uses a bond that grows from 1 to `1 + r`. It writes the no-arbitrage condition as `d < 1 + r < u`, `q = ((1 + r) − d)/(u − d)`, and discounts with `1/(1 + r)`. Its Python and C++ code, however, use `exp(r)` for `q`, for discounting and for the no-arbitrage check. The text and the code therefore describe two different markets.

**Chosen convention:** `r` is the effective simple risk-free return over the single period, and `R = 1 + r` is used everywhere (see `methodology.md` §2). A user with a continuous annual rate must convert explicitly: `R = exp(rc·T)`, `r = R − 1`.

## 2. Baseline price recalculated, not copied

The guide lists a base case of `S0 = 100, K = 100, u = 1.12, d = 0.92, r = 0.02` with "call price ≈ 8.43".

Recalculated under the simple-rate convention:

- `R = 1.02`, `q = (1.02 − 0.92)/0.20 = 0.5`
- Call payoffs are 12 in the up state and 0 in the down state.
- `C = 0.5·12/1.02 = 6/1.02 = 5.8823529412` (the value in `results/baseline/example_call.json`).

Applying the guide's own `exp(r)` code to the same inputs gives about 5.893. Neither convention produces 8.43, so the stated value is not used anywhere in this project. The test `test_guide_stated_price_is_not_reproduced` documents the discrepancy.

## 3. Unnecessary input restrictions

The guide states `u > 1` and `0 < d < 1`. It also requires `K > 0`, and one of its other projects' validators requires `r ≥ 0`. None of these is needed for the one-period model. Only `S0 > 0`, `u > d > 0` and `r > −1` are required, and `K = 0` is a valid strike. This project includes arbitrage-free scenarios in which both multipliers exceed 1, both multipliers are below 1, and the rate is negative.

## 4. Boundary arbitrage and invalid markets

The guide's code only *warns* when the no-arbitrage condition fails, and then still returns a number labelled `price`. Here, the market is classified first:

- **Both equalities contain arbitrage.** `R = d` and `R = u` are both arbitrage cases, because both states are possible: one state pays zero and the other pays strictly more.
- **No price in an arbitrage market.** When the market contains arbitrage, no value is labelled an arbitrage-free price. An algebraic replication cost is reported in a separately named field.
- **Explicit portfolios.** The arbitrage portfolios are constructed in full and verified.
- **Near-boundary cases** are reported as unresolved rather than given a confident classification.

## 5. Hedge ratio is not automatically a spot derivative

The guide writes `Δ = ∂C0/∂S0 = (Cu − Cd)/(S0(u − d))`. The fraction on the right is the exact *payoff-matching* coefficient of the one-period hedge. It is not, in general, the derivative of the model price with respect to `S0` when `u`, `d` and `K` are held fixed.

**Counter-example (baseline).** For `Sd < K < Su`, the call price is `C(S0) = q·(S0·u − K)/R`, so `∂C/∂S0 = q·u/R = 0.5·1.12/1.02 ≈ 0.549`. The replication hedge ratio is `Δ = 12/20 = 0.6`. The two numbers differ.

The two quantities coincide only in special cases. One example is when both payoffs are linear in `S_T` over the relevant range, as with `K ≤ Sd` (where both equal 1) or `K ≥ Su` (where both equal 0). This project therefore labels `Δ` as the *replication hedge ratio* throughout.

The guide also describes the hedge as "a dynamic hedging strategy". In one period it is a static hedge: set up at time 0, with no rebalancing.

## 6. No gamma

The guide gives `Γ ≈ (Δu − Δd)/(S0(u − d)/2)`. The quantities `Δu` and `Δd` are hedge ratios at second-period nodes, and those nodes do not exist in a one-period tree. No gamma is computed or reported, because there is no supported second-difference calculation in this model.

## 7. Put results built from call results

The guide's `price_put` reuses the call's replication error and builds the put's bond position from the call's. In this project, each claim (call, put, digital, generic) is replicated and verified **independently** from its own payoffs (see `tests/test_replication.py::test_put_specific_replication`).

## 8. Boundary statements about strikes

- **Put limit for large K.** The guide says "as K → ∞, put price → K/(1+r)". Once `K ≥ Su`, both states are in the money, and the put price is `K/R − S0`, not `K/R`. The test `test_high_strike_put_equals_discounted_strike_minus_S0` checks this.
- **Deep in-the-money call.** For the K = 80 case the guide writes "≈ S0 − K/(1+r)". Because `Sd = 92 > 80`, the relationship is **exact**: `21.568627 = 100 − 80/1.02` (see the `deep_itm_call` scenario).

## 9. Claims not reproduced

Project 1 ends with a résumé bullet claiming, among other things, a specific test-coverage percentage, use in teaching a stated number of analysts, and production-grade status. None of these is reproduced. This project makes no coverage, performance, deployment or professional-experience claim, and its test counts come only from `results/baseline/test_results.xml`.
