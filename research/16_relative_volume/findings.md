# Completed-minute relative-volume findings, 2026-10-01

Both tested volume hypotheses lose after execution costs. The private adapter matches a recorded cumulative volume to every one of the 1,154,473 retained shared quote observations across seven sessions. This establishes exact receipt identity, not source-event freshness.

Only the three development dates build the frozen same-time-of-day baseline. Strict freshness admits zero bars on Aug19, zero on Aug20, and three on Aug21. No time-of-day cell has three development observations, so every strict policy fails closed with no trades. Receipt-proxy mode admits 2,691, 3,673, and 3,692 bars on those dates and creates 2,229 instrument/minute baseline cells with all three days represented.

| Evaluation date | Admitted proxy volume bars | Cumulative decreases detected | Continuation trades/net Rs | Climax-reversal trades/net Rs |
|---|---:|---:|---:|---:|
| Aug24 | 2,013 | 4 | 19 / -2,503.44 | 2 / -29.66 |
| Aug25 | 2,366 | 0 | 33 / -2,524.18 | 6 / -990.85 |
| Aug31 | 0 | 7 | 0 / 0 | 0 / 0 |
| Sep1 | 1,383 | 3 | 18 / -2,549.15 | 2 / -327.04 |

Continuation totals 70 trades, Rs-2,170.22 gross P&L, Rs5,406.55 fees, and Rs-7,576.77 net P&L. Confirmed climax reversal totals ten trades, Rs-521.02 gross P&L, Rs826.53 fees, and Rs-1,347.55 net P&L. Gross P&L already includes bid/ask crossing and hypothetical extra slippage. Both policies lose before explicit fees as well as after them.

The continuation policy reaches the monetary daily loss halt on each of the three dates that admit bars. Those totals are affected by the halting rule, and cannot estimate returns from trading every signal. Aug31's sparse observation coverage fails the fixed 40-observation minute requirement. We did not reduce it after seeing missing bars. A zero-trade date is not a profitable result.

## Verification

All 16 policy/session account replays completed with no unresolved positions. Five tests passed. They cover completed-minute availability, prefix independence when future volume changes, cumulative reset rejection, three-day baseline admission, baseline copy/freeze behavior, unknown freshness, and missing volume. Some tests combine these behaviors. Python compilation passed.

The `initial-v1` evidence preserves source snapshots, common quote-cache fingerprints, private normalized-volume fingerprints, source paths, exact volume-clock semantics, rejected-minute/reset counts, fitted seasonal lookup, fixed thresholds, trades, and account summaries. Development volume never uses an evaluation session. Precomputed evaluation bars are exposed only at their actual next-minute availability observation, not before completion.

## What the result permits

This is a tested negative result for two fixed received-volume hypotheses on a small historical cohort. It does not reject all volume methods or reproduce the much longer-horizon Lee/Swaminathan study. Three seasonal observations per instrument/minute remain a weak baseline, and source-volume update time is unknown. Cumulative decreases are treated as unknown reset/correction events rather than negative traded volume. The first and final minute cannot become convenient complete bars.

Next research should collect continuous fixed-cohort volume with explicit source event clocks, reset/correction flags, and a longer formation period. Freeze baseline estimation and compare verified incremental volume against these controls on later sessions. Keep the present thresholds and losses in the record; do not make the original experiment look profitable by dropping costs, loosening admission after evaluation, or selecting only favorable instruments.
