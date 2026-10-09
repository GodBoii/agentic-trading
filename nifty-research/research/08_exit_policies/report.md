# Option exit policies, 1 October 2026

All 36 exit configurations lost after estimated costs on their priced trades. The archive supports studying when a policy would have reacted to sampled quotes. It does not support assuming that a stop executes at its threshold.

There are 2,814 priced trade records, 120 unresolved exits and 273 records with at least one missing monitoring sample across the configurations. Those records repeatedly use the same market episodes. They are not independent trades or the outcome of one combined account.

## Fixed entries and exits

The entry signal is the known five-minute futures midpoint return. Above +2 basis points the policy buys an ATM call or bull call spread. Below -2 basis points it buys an ATM put or bear put spread. The direction and contracts are selected with fresh quotes at decision time. Candidate identities remain fixed after entry.

The entry schedule uses at least thirty-one minutes between opportunities. Spacing does not depend on which exit triggers first. The maximum thirty-minute hold plus the known normal-session close defines common eligibility for every policy. This deliberately prevents a faster exit from acquiring a different set of immediate re-entry opportunities.

Entry occurs one second after the decision at the correct bid/ask side. Each leg has one 65-unit lot. Quote lookup is backward-only and permits at most two seconds of receipt-time age. Vertical spacing is fifty points. The lab strips forward return labels before the exit code receives the feature table.

The six predeclared exit policies are:

- Time only.
- Loss of 10% of initial debit or gain of 20%.
- Loss of 20% of initial debit or gain of 40%.
- Loss of 30% of initial debit or gain of 60%.
- Trailing loss of 20% of initial debit from the best previously observed whole-position gross P&L, with the initial peak set to zero.
- Directional thesis reversal, an opposite known one-minute futures return of at least two basis points.

Each has a five-, fifteen- or thirty-minute maximum horizon. Thresholds use whole-position gross liquidation P&L divided by the positive initial debit, including the bid/ask sides but before explicit taxes and brokerage. They are not percentages of account equity or individual-leg premiums.

The monitor samples every five seconds. The first observed trigger submits a conditional close one second later, when the position is repriced from the fresh backward quotes available then. Closing never substitutes a stop price or midpoint. Missing monitoring samples remain visible. If quotes are unavailable for an intended exit, the position is unresolved and that configuration halts for its remaining date.

## Results

The full gross, cost and net table is saved in [artifacts/table.md](artifacts/table.md). A fifteen-minute subset is below.

| Structure | Exit | Priced | Unknown exits | Gross INR | Costs INR | Net INR | Worst sampled adverse P&L INR |
|---|---|---:|---:|---:|---:|---:|---:|
| Single long | Time | 82 | 4 | -4,189 | 5,953 | -10,142 | -1,504 |
| Single long | Stop 10%, target 20% | 83 | 3 | -2,711 | 6,020 | -8,730 | -934 |
| Single long | Trailing 20% | 83 | 3 | -5,268 | 6,015 | -11,283 | -1,339 |
| Single long | Thesis reversal | 85 | 3 | -3,484 | 6,192 | -9,676 | -911 |
| Debit spread | Time | 75 | 3 | -3,240 | 10,637 | -13,877 | -952 |
| Debit spread | Stop 10%, target 20% | 76 | 2 | -2,681 | 10,766 | -13,447 | -467 |
| Debit spread | Trailing 20% | 76 | 2 | -3,383 | 10,764 | -14,147 | -622 |
| Debit spread | Thesis reversal | 77 | 3 | -2,519 | 10,954 | -13,473 | -580 |

Aggregate counts differ because an unresolved exit halts that configuration. Direct comparisons of their aggregate totals would mix different entry cohorts. The paired comparison instead compares identical entries whose outcomes are priced under both policies and reports unknown pairs separately.

For the fifteen-minute single-long structure, the 10% stop and 20% target improved paired net P&L by INR 1,664 across 82 priced common entries relative to time-only exits. There were four unknown pairs. Thesis reversal improved paired net P&L by INR 1,298 across the same 82 priced pairs. Both full policies still lost money.

At thirty minutes the same 10% stop and 20% target reduced paired net P&L by INR 3,302 across 72 priced single-long pairs, with nine unknown pairs. Thesis reversal reduced it by INR 1,349. Thus these dates do not support a universal statement that a tighter stop or thesis exit improves expectancy. No policy is selected from this exploratory table.

Costs also matter. Fifteen-minute debit-spread time exits incur about INR 142 estimated roundtrip costs per priced trade, compared with about INR 73 for the single-long structure. Those estimates include each leg as a separate entry and exit order. The capped expiry payoff needs to earn enough to cover that extra turnover.

## Stop overshoots and missing observation

There are 233 priced records with a positive stop or trailing overshoot. The maximum ordinary 10% stop overshoot for single longs was about INR 247. The maximum trailing overshoot was INR 416. These are differences between the gross P&L threshold and the eventual quoted gross liquidation P&L. They do not include an additional real fill error beyond the replay's assumptions.

The INR 416 example occurs on August 12. A long 24,450 call entered at 14:42:01 IST. The sampled trailing rule triggered at 15:08:46 and the conditional exit repriced at 15:08:47. Its gross trailing threshold was INR 1,033.50, while gross closing P&L was INR 617.50. There were 110 missing five-second monitoring samples before the exit. The record cannot establish when an actual continuous monitor would first have triggered during that interruption. Filling at the threshold would hide both the data gap and the eventual price difference.

Five-second sampled adverse excursion is a lower bound on observed path risk. It can miss a worse move between samples. Receipt-time freshness also does not establish the exchange age of the recorded bid/ask.

## Stopping-time interpretation

For observed whole-position P&L P, initial debit D, stop s and target g, the sampled exit decision is:

\[
\tau = \min\{t:\ P_t\leq-sD\ \text{or}\ P_t\geq gD\ \text{or}\ t\geq T\}.
\]

The quote replay then values the close at tau plus one second. It never equates the threshold with the closing price. A trailing rule replaces the loss threshold with past maximum P minus its declared debit fraction. The thesis rule uses the latest known minute return, with at most sixty seconds of decision-time age.

[Carr and Lopez de Prado](https://arxiv.org/abs/1408.1159) discuss rule calibration and overfitting under a specified OU process. [Lipton and Lopez de Prado](https://arxiv.org/abs/2003.10502) derive optimal boundaries for an OU setting. Neither paper establishes that these Nifty option premiums follow OU dynamics, or that its optimal boundaries transfer to this archive. This experiment tests simple fixed policies without tuning a process or picking the most profitable threshold.

The original [Backtesting.py implementation](https://github.com/kernc/backtesting.py/blob/master/backtesting/backtesting.py) and [VectorBT documentation](https://vectorbt.dev/api/portfolio/base/) expose execution timing and stop ordering as explicit modelling choices. This custom study uses sampled quote order instead of inventing an intra-candle price path. It does not claim to validate or reproduce those libraries.

## Verification and research decision

Nine tests pass. They cover the first observed threshold, a missing-sample overshoot, bid/ask closing, one-second exit latency, fixed contract identity, retained unpriced positions, causal thesis freshness, entry schedules independent of forward labels and trailing thresholds based on past peaks. A test caught a timestamp-unit mismatch in the standalone thesis lookup, which was corrected before completion.

The research decision is to keep exits explicit and separate from entry selection. None of these exits repairs the tested momentum entry's negative net outcome. Whole-position stops can reduce some observed adverse excursions, but risk reduction and improved expectancy are separate findings. Better entry valuation and fresh validation data remain necessary before comparing deployable policies.
