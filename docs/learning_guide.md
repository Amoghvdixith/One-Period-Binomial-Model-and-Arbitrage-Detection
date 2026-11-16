# Learning guide

This guide explains the ideas behind the code in plain language. All numbers refer to the baseline market (`S0 = 100, u = 1.12, d = 0.92, r = 0.02, K = 100`) and match the files in `results/baseline/`.

## 1. What a one-period binomial model represents

It is the smallest model with uncertainty that still has a fully worked-out pricing theory. Today the stock costs `S0 = 100`. Tomorrow, which is the only future date, it is worth either `Su = 112` or `Sd = 92`. Cash grows from 1 to `R = 1.02` with certainty.

The model isn't meant to be realistic. It's a laboratory where you can see, exactly and without approximation, why derivative prices are what they are.

## 2. Why `d < R < u` matters

Compare the stock's two possible growth factors with cash's single one:

- **`R ≤ d`:** the stock grows at least as fast as cash even in its *worst* state. Take `u = 1.25, d = 1.05, r = 0.02` (scenario `r_below_d`). Borrow 100, buy one share, and you owe 102 tomorrow. The share is worth 125 or 105, so you gain 23 or 3 and can never lose. That is an arbitrage.
- **`R ≥ u`:** cash beats the stock even in the stock's *best* state. Short one share and deposit the 100 proceeds.
- **`d < R < u`:** each asset beats the other in some state, so neither dominates and no free lunch exists.

## 3. Risk-neutral versus real-world probability

`q = (R − d)/(u − d) = 0.5` in the baseline. It is **not** the chance that the stock goes up; the model never even needs that chance. `q` is the unique weighting under which the stock, on average, grows exactly like cash: `0.5·112 + 0.5·92 = 102 = 1.02·100`.

Pricing with `q` and discounting at `R` gives the price that rules out arbitrage. That works whatever investors believe about the real-world probabilities.

## 4. State prices versus probabilities

A **state price** is what you would pay today for 1 unit delivered in one state only:

- Baseline: `π_up = π_down = 0.5/1.02 ≈ 0.4902`.
- They add up to `1/R ≈ 0.9804`, which is the price of 1 delivered for sure. They don't add up to 1.

They are prices, not probabilities. Any claim's price is `π_up·Xu + π_down·Xd`. For example, the call is `0.4902·12 + 0.4902·0 ≈ 5.8824`.

## 5. Replication and market completeness

With two states and two traded assets, any payoff pair `(Xu, Xd)` can be built exactly from stock and cash. A market where every claim can be replicated like this is called **complete**.

The baseline call is replicated by `Δ = 0.6` shares plus `B ≈ −54.12` in cash, i.e. 54.12 borrowed:

- **Up state:** `0.6·112 − 54.12·1.02 = 67.2 − 55.2 = 12` ✔
- **Down state:** `0.6·92 − 55.2 = 0` ✔
- **Cost today:** `0.6·100 − 54.12 = 5.8824`, exactly the risk-neutral price.

Two portfolios with identical payoffs must cost the same, or there is arbitrage. That is the law of one price.

## 6. Borrowing versus holding cash

`B` is the amount placed in the cash account **today**:

- `B > 0` means lending (holding cash). The put's replica has `B ≈ +43.92`.
- `B < 0` means borrowing. The call's replica has `B ≈ −54.12`.

Tomorrow the cash position is worth `B·R`. Don't confuse `B` with that terminal amount.

## 7. Short selling

A negative share holding means selling a share you don't own and buying it back tomorrow. The put's replica holds `Δ = −0.4` shares. Shorting brings in cash today (`+0.4·100 = 40`) and costs the terminal stock value tomorrow.

The model assumes short selling has no fees or restrictions, which real markets don't guarantee.

## 8. Exact hedge ratio versus spot sensitivity

`Δ = (Xu − Xd)/(Su − Sd)` is the share holding that makes the hedge match the claim **exactly in both states**. It is a static, one-period hedge: set it up once, never rebalance.

It is tempting to call `Δ` "the derivative of the price with respect to `S0`", but in general that is not the same thing. With `u` and `d` fixed, the baseline call's price changes at rate `q·u/R ≈ 0.549` per unit of `S0`, while `Δ = 0.6`.

The two differ because moving `S0` also moves `Su` and `Sd` relative to the fixed strike. There is also no "gamma" here, because there are no further tree nodes.

## 9. Why the equality cases can contain arbitrage

If `R = d` exactly (e.g. `d = 1.02` with `r = 0.02`), borrowing 100 to buy one share gives:

- **Up state:** `112 − 102 = 10`.
- **Down state:** `102 − 102 = 0`.

You never lose money and you sometimes gain, at zero cost. That still counts as an arbitrage, provided the up state can actually happen. This is why the no-arbitrage condition is **strict** (`<`, not `≤`), and why the code reports `q = 0` or `q = 1` as not arbitrage-free.

## 10. How quote arbitrage works

Suppose someone quotes the baseline call at `M = 6.50` while its replication cost is `V ≈ 5.8824`:

- Sell the call (+6.50).
- Build its replica for 5.8824.
- Deposit the difference, 0.6176.

Tomorrow the replica pays exactly what you owe on the call, and the deposit pays `0.6176·1.02 = 0.63` in either state. That is a certain profit for zero outlay. If the quote were too low, you would reverse every leg. The saved file `quote_arbitrage.csv` lists each leg.

Real markets add bid–ask spreads, fees, margin and execution risk. A model discrepancy is not proof that a real trade works.

## 11. What changes in a multi-period model (not implemented here)

In a multi-period tree:

- Each node is a one-period model of exactly this kind.
- Prices are found by working backwards from expiry, node by node.
- The replicating portfolio must be **rebalanced** at every node. That is dynamic hedging, which only appears with more than one period.
- Hedge ratios at neighbouring nodes exist, so differences of them, including tree-based gamma estimates, start to make sense.
- With many short periods and suitable `u`, `d`, prices converge to continuous-time models.

American exercise, dividends and calibration also enter at that stage. All of these are out of scope here.

## 12. Interview self-check questions

1. State the no-arbitrage condition for a one-period binomial model and explain why it must be strict.
2. Given `S0 = 50, u = 1.2, d = 0.9, r = 0.05`, compute `q`, the state prices, and the price of a call struck at 50.
3. Why does `q` contain `R = 1 + r` rather than `r`? What changes if a continuously compounded rate is given?
4. Construct the replicating portfolio for a put in the baseline market. Is the cash position borrowing or lending?
5. Why do state prices sum to `1/R`? Why aren't they probabilities?
6. Is the replication hedge ratio always equal to `∂price/∂S0`? Give an example where they differ.
7. If `u = 1.05, d = 0.98, r = 0.10`, write down an explicit arbitrage and its payoffs.
8. A call is quoted 0.40 below its replication cost. List the legs of the arbitrage and its profit in each state.
9. Why can put–call parity, `C − P = S0 − K/R`, be checked without knowing `q`?
10. What new ideas (rebalancing, path dependence, early exercise) appear when you move to two periods?
