# Methodology

This document defines the model, conventions, formulas and numerical policies that the code in `src/binomial_arbitrage/` implements.

## 1. The two-state model

There is one period, from time 0 to time 1, and two traded assets:

| Asset | Time 0 | Time 1, up state | Time 1, down state |
|---|---|---|---|
| Stock | `S0` | `Su = S0·u` | `Sd = S0·d` |
| Cash account (per unit deposited) | `1` | `R` | `R` |

Inputs: `S0 > 0`, `u > d > 0`, `r > −1`, and for strike-based claims `K ≥ 0` and `cash_payout ≥ 0`.

"Up" and "down" describe **relative ordering only** (`Su > Sd`). Both states may be gains (`u > d > 1`) or both may be losses (`1 > u > d`). The model does **not** require `u > 1`, `d < 1` or `r ≥ 0`.

Assumptions: frictionless trading, unrestricted short selling, one borrowing and lending rate, fractional positions, no dividends, and both terminal states possible.

## 2. Interest-rate convention

```
r = effective simple risk-free return over the single model period
R = 1 + r          (cash B deposited at time 0 is worth B·R at time 1)
```

There is no annualisation and no maturity parameter, and `exp(r)` is never used in place of `1 + r`. Validation requires `r > −1`, i.e. `R > 0`.

If you start from a continuously compounded annual rate `rc` and a maturity `T`, convert explicitly before using the model:

```
R = exp(rc · T)
r = R − 1
```

This conversion is documented here but deliberately not implemented, so the two conventions can never be mixed silently.

## 3. No-arbitrage condition

The market is arbitrage-free **if and only if**

```
d < R < u      (strict)
```

- If `R ≤ d`, the stock does at least as well as cash in both states and strictly better in the up state. Buying the stock and borrowing is an arbitrage.
- If `R ≥ u`, cash does at least as well as the stock in both states and strictly better in the down state. Shorting the stock and depositing the proceeds is an arbitrage.
- Both equality cases (`R = d` and `R = u`) contain arbitrage because both states are assumed possible. The arbitrage gives a zero payoff in one state and a strictly positive payoff in the other.

Every market is assigned exactly one status:

| Status | Meaning |
|---|---|
| `arbitrage_free` | `d < R < u` strictly, and not within the near-boundary tolerance |
| `arbitrage_R_le_d` | `R ≤ d` (includes exact `R = d`, flagged `R_equals_d`) |
| `arbitrage_R_ge_u` | `R ≥ u` (includes exact `R = u`, flagged `R_equals_u`) |
| `near_boundary_unresolved` | `R` lies within the relative tolerance of `d` or `u` but is not exactly equal |
| `invalid_input` | inputs fail validation; no model is built |

A market that contains arbitrage is **not** an input error. It stays fully analysable, and the explicit arbitrage portfolio is produced.

## 4. Risk-neutral probability

```
q = (R − d) / (u − d)
```

`q` is always reported as `q_candidate`, and it is **never clipped**. It is a valid risk-neutral probability, with `0 < q < 1`, only when the status is `arbitrage_free`. In every other market, values such as `q = 0`, `q = 1`, `q = −0.15` or `q = 1.71` are reported with a flag saying they are not probabilities.

`q` is not a forecast of real-world likelihood. It is the unique weight that makes the discounted stock price a martingale: `q·Su + (1 − q)·Sd = R·S0`.

## 5. Pricing and state prices

For a claim paying `Xu` in the up state and `Xd` in the down state, in an arbitrage-free market:

```
price    = [q·Xu + (1 − q)·Xd] / R
pi_up    = q / R
pi_down  = (1 − q) / R
```

The code checks these identities:

```
pi_up + pi_down        = 1/R
pi_up·Su + pi_down·Sd  = S0
price                  = pi_up·Xu + pi_down·Xd
```

State prices are **prices** (the time-0 cost of receiving 1 unit in a single state). They sum to `1/R`, not to 1, so they are not probabilities.

When the market is not arbitrage-free, `arbitrage_free_price` is `None`. The algebraic replication cost is reported in a separately named field labelled *"algebraic replication cost – NOT an arbitrage-free market valuation"*, and the market's own diagnosis is kept.

## 6. Payoffs

| Claim | `X(S_T)` |
|---|---|
| European call | `max(S_T − K, 0)` |
| European put | `max(K − S_T, 0)` |
| Cash-or-nothing digital call | `cash_payout · 1{S_T > K}` (**strict** inequality: `S_T = K` pays nothing) |
| Generic | any finite `(Xu, Xd)`, which may be negative |

Terminal prices are formed in exact arithmetic, so a strike that equals a terminal price exactly is handled exactly.

## 7. Replication

Solve the two equations

```
Δ·Su + B·R = Xu
Δ·Sd + B·R = Xd
```

which give

```
Δ    = (Xu − Xd) / (Su − Sd)                 shares of stock
B    = (u·Xd − d·Xu) / ((u − d)·R)           currency placed in the cash account AT TIME 0
cost = Δ·S0 + B
```

`B < 0` means borrowing. `B` is the time-0 amount; at time 1 it is worth `B·R`.

Verification is done independently, state by state: `portfolio_up = Δ·Su + B·R` and `portfolio_down = Δ·Sd + B·R` are compared with `Xu` and `Xd`. The output records the signed errors, the maximum absolute error, and a second solution from `numpy.linalg.solve`, together with its condition number. Each claim is replicated separately; the put never reuses the call's results.

`Δ` and `B` are formed in exact rational arithmetic and rounded once. The verification then runs in ordinary floating point. Exact formation matters for narrow state separations, where `float(u) − float(d)` loses digits.

**Hedge ratio versus spot sensitivity.** `Δ` is the exact payoff-matching coefficient of a *static, one-period* hedge. It is set up once at time 0 and never rebalanced. It is not automatically `∂price/∂S0` with `u` and `d` held fixed. For a call with `K` strictly between `Sd` and `Su`, the price `q·(S0·u − K)/R` has derivative `q·u/R`, which differs from `Δ` in general (see `reference_corrections.md`). No gamma is computed, because a one-period tree has no second-period nodes to difference.

## 8. Explicit stock/cash arbitrage

| Case | Positions | Initial cost | Up payoff | Down payoff |
|---|---|---|---|---|
| A: `R ≤ d` | +1 share, borrow `S0` | 0 | `S0·(u − R)` > 0 | `S0·(d − R)` ≥ 0 |
| B: `R ≥ u` | −1 share, deposit `S0` | 0 | `S0·(R − u)` ≥ 0 | `S0·(R − d)` > 0 |

Payoffs are computed in exact rational arithmetic. A portfolio is reported as **verified** only if all three checks pass:

1. The initial cost is 0 within `payoff_abs_tol`.
2. Both payoffs are nonnegative. This check is **exact**, with no tolerance, so a tiny negative payoff can never pass.
3. At least one payoff exceeds `payoff_abs_tol`.

For a `near_boundary_unresolved` market, the candidate portfolio on the mathematically indicated side is still built and checked, but the market status stays unresolved.

## 9. Quote arbitrage

Quote arbitrage is assessed only when the stock/cash market is `arbitrage_free`. Otherwise the result is `not_assessed`, and the message keeps the underlying diagnosis. Let `M` be the quoted price and `V` the replication cost. The comparison tolerance is `quote_abs_tol + quote_rel_tol·max(|M|, |V|)`.

| Case | Legs |
|---|---|
| `M > V` (overpriced) | short 1 claim (+M), buy Δ shares (−ΔS0), cash leg B (−B), deposit `M − V` |
| `M < V` (underpriced) | buy 1 claim (−M), short Δ shares (+ΔS0), cash leg −B (+B), deposit `V − M` |

In both cases the net initial cost is 0 and the net terminal payoff is `|M − V|·R` in **each** state. Every leg's time-0 cash flow and both terminal payoffs are saved, and the sums are checked state by state. If `|M − V|` is within tolerance, the result is "no discrepancy detected at the specified tolerance".

This is a frictionless model statement. It is not evidence that any real quote can be traded.

## 10. Tolerance and conditioning policy

Exact mathematical inequalities are kept separate from numerical warnings.

| Tolerance | Default | Units | Use |
|---|---|---|---|
| `near_boundary_relative_gap` | 1e-10 | dimensionless, `min(|R−d|, |u−R|)/(u−d)` | a nonzero gap below this → `near_boundary_unresolved` |
| `min_relative_state_separation` | 1e-12 | dimensionless, `(u−d)/u` | below this → rejected as ill-conditioned |
| `narrow_relative_state_separation` | 1e-6 | dimensionless, `(u−d)/u` | below this → `narrow_state_separation` warning |
| `payoff_abs_tol` | 1e-9 | currency units | zero-cost test and strict-gain test for arbitrage portfolios |
| `quote_abs_tol`, `quote_rel_tol` | 1e-9, 1e-9 | currency units, dimensionless | quote comparison |
| `replication_abs_tol` | 1e-9 | currency units, scaled by `1 + max(|Xu|, |Xd|)` | replication check pass/fail |

**Exact classification.** Inputs are converted to `Decimal`: JSON is parsed with `parse_float=Decimal`, and Python floats go through their shortest representation, `Decimal(repr(x))`. Classification then compares `R`, `d` and `u` as exact `fractions.Fraction` values. This is why `d = 1.02` with `r = 0.02` is detected as exactly `R = d`, even though `1 + 0.02 != 1.02` in binary floating point. Exact equality is never reported as "unresolved".

**Conditioning.** A state separation `u = d` is rejected as degenerate. A positive but extremely small separation is rejected as ill-conditioned rather than silently divided by.

## 11. Sensitivity analysis

- **Strike sweep:** K from 70 to 130 in steps of 1, on the baseline market. Reports call and put prices, replication hedge ratios, cash positions and the put–call parity residual.
- **Rate sweep:** r from −0.15 to 0.20 in steps of 0.005. Prices appear only where the market is `arbitrage_free`. The exact boundaries `r = d − 1` and `r = u − 1` fall on the grid.
- **(u, d) grid:** u from 0.80 to 1.40 and d from 0.60 to 1.20, both in steps of 0.01, with r fixed at the baseline value. Cells with `u ≤ d` are `invalid_input` and masked. Call prices appear only on `arbitrage_free` cells.

All sweep points are generated with exact `Decimal` steps.
