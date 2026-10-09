# Exit comparison findings

October 1, 2026. Changing fixed exits does not rescue the baseline strategy on these recordings. All three whole-account receipt-proxy variants lose before fees. A second comparison on identical entries isolates exit differences and also loses for every variant.

## Evidence completed

The initial shared-runner experiment completed 42 policy/session replays, three frozen settings across seven dates in strict and receipt-proxy modes. Each setting saw the same 1,154,473 retained observations. Every account replay ends complete with zero unresolved positions and pending entries.

The paired study freezes the baseline's 155 actual simulated receipt-proxy entries, including timestamps, prices and quantities. All three exit settings run on these same entries for 465 completed counterfactual outcomes across 21 date/variant groups. Entry equality, journal/source hashes and gross-minus-fees accounting pass in `runs/paired-exits-v1/verification.json`. No counterfactual exposure remains unresolved.

Fifteen behavior and mathematics tests pass. They verify required success probabilities, impossible cost hurdles, invalid inputs, identical synthetic raw signal streams, delayed execution, stop overshoot, target-price drift, short-side exits, frozen quantity, missing future quotes, pre-entry causality and agreement with the account engine in a no-loss-action example. Test output is `test-results.txt`. Compilation passes.

The raw policy reason counters match across all three exit variants on every actual session and mode. All 28 non-baseline comparisons pass in `entry-stream-verification.json`. This verifies entry-rule consistency; account admission still differs because exits affect sizing, slots, cooldown and loss actions.

## Whole-account receipt-proxy result

Amounts are rupees summed over separate daily accounts. Source quote age remains unverified. Entry and exit prices are delayed observed bid/ask proxies with hypothetical slippage, not actual broker fills.

| Exit settings, target/stop/seconds | Trades | Gross P&L | Fees | Net P&L |
| --- | ---: | ---: | ---: | ---: |
| 30/15/300 | 155 | -5,944.02 | 11,698.51 | -17,642.53 |
| 60/30/300 | 151 | -6,390.68 | 11,486.27 | -17,876.95 |
| 30/15/60 | 174 | -4,889.65 | 13,055.14 | -17,944.79 |

| Settings | Development net | Diagnostic validation net | Historical audit net |
| --- | ---: | ---: | ---: |
| 30/15/300 | -7,614.52 | -5,018.86 | -5,009.16 |
| 60/30/300 | -7,612.29 | -5,039.03 | -5,225.63 |
| 30/15/60 | -7,755.30 | -5,126.47 | -5,063.02 |

Shorter holding improves gross accounting here but admits nineteen more trades than baseline and pays more fees. Its whole-account net result is slightly worse. That observation cannot be explained solely as an exit effect on unchanged quantities.

Strict mode has only two trades per setting, all on August 25. Baseline and doubled distances each net -905.93; the sixty-second setting nets -446.78. Two trades under sparse recorded eligibility cannot estimate expected live performance. The largest marked drawdown across initial proxy account runs is Rs 2,910.39 despite the Rs 2,500 loss-action threshold, because fills follow delayed observations.

## Identical-entry counterfactual result

This comparison excludes portfolio loss actions and allows overlapping positions that may violate actual account limits. It diagnoses exit paths and is not a tradeable portfolio.

| Settings | Same entries | Gross P&L | Fees | Net P&L | Target / stop / time exits |
| --- | ---: | ---: | ---: | ---: | --- |
| 30/15/300 | 155 | -6,244.22 | 11,697.50 | -17,941.72 | 10 / 62 / 83 |
| 60/30/300 | 155 | -7,235.85 | 11,699.48 | -18,935.33 | 2 / 15 / 138 |
| 30/15/60 | 155 | -4,474.10 | 11,697.41 | -16,171.51 | 1 / 13 / 141 |

On these fixed quantities, sixty-second exits lose Rs 1,770.21 less than the baseline exits, but still lose Rs 16,171.51. Wider distances lose Rs 993.61 more. The paired baseline differs from the whole-account baseline because the paired study deliberately excludes the latter's daily-loss exit actions.

These are descriptive sensitivities on previously inspected historical dates. They do not establish that sixty seconds is optimal. The hypotheses remain frozen; no threshold selection follows from this ordering.

## Mathematical interpretation

The two-outcome break-even formula is p = (S+C)/(T+S), where T is target, S stop and C round-trip cost. A two-to-one gross ratio does not imply positive expected returns. With thirty/fifteen-basis-point barriers and ten-basis-point costs, it needs roughly 55.6% success, before accounting for time exits, variable quantity and missed execution.

The [trailing-stop paper](https://arxiv.org/pdf/1701.03960) derives stopping regions under explicit diffusion assumptions. The [transaction-cost and mean-reversion paper](https://arxiv.org/pdf/1411.5062) couples optimal entry and exit for a modeled spread. These sources motivate evaluating joint behavior. This study does not calibrate their processes or implement their analytical boundaries. Constant doubled distances are not volatility-scaled or ATR exits.

## Exact evidence locations

- `research/11_exit_math/runs/initial-v1/plan.json`, source snapshot, input manifests, 42 summaries and trade journals.
- `research/11_exit_math/runs/initial-v1/comparison.csv` and `aggregate.json` retain all modes and chronological groups.
- `research/11_exit_math/runs/paired-exits-v1/plan.json` preserves the same seven tape hashes, all baseline journal hashes and paired-code snapshots.
- `research/11_exit_math/runs/paired-exits-v1/comparison.csv` and 21 outcome files preserve every counterfactual.
- `research/11_exit_math/runs/paired-exits-v1/verification.json` checks all entry sets, completed outcomes and accounting.

Next collect independently evaluated timing-verified sessions and model expected executable movement over several preregistered horizons. If adaptive exits are pursued, estimate volatility from strictly prior events and freeze per-position risk before submission. Preserve the full account and paired exit views because each answers a different question.
