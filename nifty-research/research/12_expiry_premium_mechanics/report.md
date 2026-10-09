# Expiry, quote shapes and premium mechanics

Research date: 2 October 2026. This separate study tests discrete option-price consistency, expiry-distance summaries and fixed-strike straddle changes. It uses the existing archive and study03's parity-valid cohort. It fits no variance forecast and places no trades.

The strongest finding concerns measurement. Restricting capture-time skew from two seconds to 0.25 seconds removes most whole-slice IV observations and almost all conditional quote-bound flags. The archive can support fixed two-leg premium comparisons more readily than a synchronised volatility surface.

## Scope and coverage

The run produces 243,308 quote-shape checks across both receipt-skew allowances and assumed rates of 0% and 10%. It observes 2,766 complete futures minutes on fourteen dates with option caches. Two dates have no option cache. Every fresh snapshot contains at least some quotes.

There are 2,860 revalidations of study03's 1,430 priced fixed-strike straddles across two skew allowances. All 1,430 retain their original prices under the two-second allowance. The stricter allowance retains 1,217 and rejects 213 for receipt skew. These are repeated, overlapping observations, not independent trades or one account's cumulative performance.

Every status remains in [results.json](artifacts/results.json). The [numerical tables](artifacts/numerical-results.md) retain all populated DTE/horizon cells. Row-level artifacts preserve contracts, times, weights and each diagnostic. Calendar DTE is zero on the recorded expiry date, and valuation time ends at 15:30 IST.

## Discrete quote-shape experiment

For same-expiry strikes K1<K2, call values decrease and put values increase with strike. Their vertical values lie between zero and discounted strike width. For K1<K2<K3, convexity requires

\[
\lambda V(K_1)+(1-\lambda)V(K_3)-V(K_2)\geq0,
\quad \lambda=(K_3-K_2)/(K_3-K_1).
\]

This works for unequal strike spacing. Both calls and puts have nonnegative terminal butterfly payoffs with these weights. The pricing relationships are discussed in the original [Gatheral and Jacquier paper](https://arxiv.org/html/1204.0646v4), and the tests verify the payoff identities directly. We do not fit their SVI parameterisation.

Each captured expiry and option type remains separate. We examine every adjacent captured strike pair and every consecutive triple, so passing the test is only a local necessary check. It does not prove that a full surface exists or is globally consistent.

Midpoint violations and bid/ask interval violations remain separate. Acquiring a lower-bound portfolio pays asks on positive legs and receives bids on negative legs. Selling an upper-bound portfolio receives bids on positive-position legs and pays asks to cover negative-position legs. We flag only an interval entirely outside the theoretical bound. Midpoint prices alone never determine a quote-side flag.

At each minute, lookup uses receipts at or before the decision, aged no more than two seconds. Each tested portfolio also requires its component receipt times to differ by no more than the declared skew allowance. This does not verify synchronised exchange-origin quotes. Origin timestamps, quoted quantities, queue position, actual fills, taxes, margin and financing are unavailable to this diagnostic.

At the 0% rate assumption:

| Receipt skew allowance | Family | Receipt-valid checks | Midpoint-only violations | Conditional quote-bound flags |
|---:|---|---:|---:|---:|
| 0.25 seconds | Vertical lower/monotonic | 7,581 | 0 | 0 |
| 0.25 seconds | Vertical upper | 7,581 | 4 | 1 |
| 0.25 seconds | Butterfly convexity | 1,716 | 0 | 0 |
| 2 seconds | Vertical lower/monotonic | 22,119 | 0 | 0 |
| 2 seconds | Vertical upper | 22,119 | 11 | 7 |
| 2 seconds | Butterfly convexity | 16,589 | 4 | 1 |

The two-second vertical flags all involve puts on expiry dates. The largest quote-side excess above a fifty-point vertical bound is 2.35 points on August 4, with receipt skew about 0.922 seconds. The only convexity flag occurs at the same minute, with component skew about 1.126 seconds. Tightening skew removes both.

The remaining strict vertical flag occurs on August 18 at 15:23 IST. Its quoted put vertical proceeds are 50.40 points against the zero-rate fifty-point terminal bound, and receipt skew is about 0.188 seconds. That difference equals INR 26 for a 65-unit lot before costs. It is a data-quality lead, not evidence of obtainable arbitrage or fill capacity. A contemporaneous quote origin and executable quantities would be needed even to assess the observation.

The 10% discount assumption adds one vertical-upper flag in each skew cohort. Lower bounds and convexity do not depend on that discount cap and have unchanged counts. Rates are stated sensitivities, not inferred historical financing rates. All quote-shape date means and rates remain in the JSON, including cells with no flags.

## Local IV wing differences are underidentified

The code uses study03's parity logic to infer a common same-expiry forward interval from matched call/put strikes. It then checks that the entire captured slice satisfies the declared receipt-skew allowance. Only then does it invert OTM call and put midpoint prices using the reused [Black implementation](https://vollib.org/documentation/1.0.3/_modules/py_vollib/ref_python/black.html).

At two seconds, 488 observations have both local OTM wings, 62 lack a wing, 2,215 fail the parity interval and one has no matched pairs. At 0.25 seconds, only two observations survive as whole-slice wing IV measurements. Another 609 fail whole-slice synchronisation, 2,154 fail parity intervals, and one has no matched pairs.

The two strict survivors are on August 19 and 20. Their local put IV exceeds local call IV by about 0.609 and 0.478 percentage points respectively. Two observations cannot establish typical skew, a tradable wing preference or an expiry effect. The wider allowance's DTE averages remain exported for inspection, but interpreting them as an accurate surface would ignore the synchronisation failure.

These wing measurements use the farthest captured OTM put and call relative to the inferred forward. Distances are unequal and vary with spot. They are local wing differences, not fixed-delta risk reversals, broad-tail skew or an estimate of a risk-neutral density. The archive's five-strike neighbourhood cannot support a full smile calibration.

The theoretical parity and Black references are [Stoll's original paper](https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.1969.tb01694.x) and [Black's original publication](https://www.sciencedirect.com/science/article/pii/0304405X76900246). The local implementation also uses [QuantLib's primary source](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/blackformula.cpp) as a reference. We did not run an external trading repository or substitute the monthly futures price for a weekly option forward.

## Fixed-strike compression versus observed movement

The premium experiment reuses only study03's parity-valid priced observations. Each call and put ID, strike and expiry must agree at decision, entry one second later, and exit after 5, 15 or 30 minutes. It rechecks freshness and receipt skew at all three times. It explicitly checks that reconstructed entry mid and midpoint change match the source observations. No strike rolls back to a new ATM level after movement.

Compression is negative midpoint change divided by initial straddle midpoint. Positive values mean the same contracts became cheaper. Absolute futures movement is observed movement of the recorded monthly future over the same minute endpoints. It is not same-expiry spot movement or delta-hedged P&L. The exported movement buckets use a fixed threshold of ten percent of entry premium, with every populated bucket retained.

Every headline below averages each date's mean equally, with all contributing dates retained. This differs from study03's pooled row weighting.

| Hold minutes | Expiry observations/dates, strict skew | Expiry mid change, points | Expiry compression | Nonexpiry mid change, points | Nonexpiry compression |
|---:|---|---:|---:|---:|---:|
| 5 | 27 / 3 | +0.009 | -1.066% | -0.280 | 0.166% |
| 15 | 19 / 3 | -2.440 | 2.502% | -1.130 | 0.639% |
| 30 | 11 / 2 | -4.570 | 3.604% | -2.007 | 1.064% |

Percent compression averages ratios and need not have the same sign as average point change. Initial premium and sample counts differ by date.

Long-straddle day-equal net means remain negative in every DTE/horizon cell. Strict zero-DTE short-straddle day-equal means are about INR +9.70 at fifteen minutes and INR +147.64 at thirty minutes. Those signs require careful interpretation. Study03's pooled short-straddle means in these cells were negative, and this reaggregation does not turn them into a portfolio profit.

The strict thirty-minute expiry cohort has nine overlapping observations on August 4 and two on August 11. August 4's within-date average midpoint change is +0.997 points and short net mean INR -213.48. August 11's mean change is -10.1375 points and short net mean INR +508.76. Equal weighting gives those two dates the same influence. Their different outcomes and sparse coverage prevent selecting an expiry-selling strategy. The two-second cohort has twelve observations on the same two dates and shows the same weighting sensitivity.

Net values reuse study03's declared one-lot bid/ask and estimated-cost calculations. They include four orders and its slippage assumption. They exclude margin, financing, execution capacity, rejected legs and account exposure. Requiring future priced coverage makes this a selected descriptive cohort. Neither positive nor negative conditional mean establishes an implementable entry rule.

## Sampled activity and spreads

The available complete-minute cohort contains 595 expiry-date minutes on four dates and 2,171 nonexpiry minutes on ten dates. Captured-neighbourhood option spreads average about 0.145 premium points on expiry dates and 0.221 on nonexpiry dates under equal date weighting. Mean absolute recorded futures minute returns are about 1.297 and 1.022 basis points respectively.

These figures describe captured intervals. Expiry recordings include different dayparts from nonexpiry recordings. Option prices and moneyness differ, and one nonexpiry date, July 30, contains only one complete minute. It receives a full date weight in the principal table. The JSON therefore also records a sensitivity requiring at least sixty complete minutes per date. The one-minute sample is visible rather than silently excluded. No causal expiry effect is estimated.

Option receipt counts average roughly 727 and 734 per minute by date group. Those are broker recording messages across about ten captured IDs, not exchange trades, quote changes or evidence that option trading activity is equal. The cache lacks option traded-volume increments, so it cannot estimate that comparison. Futures activity uses recorded cumulative-volume increments and carries its own aggregation limits.

Study03's inherited parity-IV cohort has only 36 expiry observations across four dates, including one date with a single IV observation. Its day-equal IV is about 21.09% on expiry dates versus 10.43% on nine nonexpiry dates. These unequal small cohorts and annualisation near expiry make the figures unsuitable as a volatility-risk-premium estimate. They remain descriptive context alongside the stricter synchronisation failures.

## Verification and implications

Twelve focused tests pass. They verify a Black-generated convex surface, call/put payoff bounds, unequal-strike butterfly payoffs, a midpoint violation covered by bid/ask, correct quote sides for an upper bound, backward freshness, stale and future rejection, receipt skew, same expiry, fixed identity, flat-volatility parity wing recovery and gapped-index day weighting. A fixed-straddle test checks unchanged IDs and retained missing-exit status.

The report and code distinguish necessary payoff relationships, quote-side consistency and conditional P&L. None is automatically a trade. The useful architecture addition is an option-candidate quality check that records quote origins, matched timestamps, fixed identities and shape failures before interpreting premiums. The current archive's whole-slice synchronisation failure prevents treating local skew as a stable agent input. Fresh surface-quality data and new expiry dates are required before promoting a wing hedge or expiry-premium entry rule.
