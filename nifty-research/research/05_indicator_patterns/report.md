# Fixed indicator and pattern hypotheses

Six fixed rules at three horizons. No parameter search or best-rule promotion. Dates from August 4 onward were already viewed in experiment 1 and are development data.

| Rule | Horizon | Labelled / unresolved | Mean signed bps | Equal-day mean bps | Holm p |
|---|---:|---:|---:|---:|---:|
| ema_8_21 | 1 | 1506 / 13 | -0.035 | -0.047 | 1.000 |
| ema_8_21 | 5 | 298 / 13 | -0.268 | -0.013 | 1.000 |
| ema_8_21 | 15 | 96 / 13 | -1.272 | -0.484 | 1.000 |
| rsi_14_reversal | 1 | 160 / 1 | -0.042 | 0.071 | 1.000 |
| rsi_14_reversal | 5 | 51 / 1 | -0.075 | -0.141 | 1.000 |
| rsi_14_reversal | 15 | 24 / 3 | 1.051 | 0.249 | 1.000 |
| bollinger_20_reversal | 1 | 171 / 0 | 0.039 | 0.257 | 1.000 |
| bollinger_20_reversal | 5 | 81 / 2 | 0.098 | 0.158 | 1.000 |
| bollinger_20_reversal | 15 | 52 / 7 | 0.295 | -0.031 | 1.000 |
| donchian_20_breakout | 1 | 213 / 1 | -0.031 | -0.300 | 1.000 |
| donchian_20_breakout | 5 | 110 / 4 | -0.288 | -0.473 | 1.000 |
| donchian_20_breakout | 15 | 60 / 8 | -0.760 | -0.612 | 1.000 |
| opening_15_breakout | 1 | 285 / 1 | 0.000 | 0.000 | n/a |
| opening_15_breakout | 5 | 58 / 1 | 0.104 | 0.104 | n/a |
| opening_15_breakout | 15 | 20 / 1 | 0.440 | 0.440 | n/a |
| return_5_reversal | 1 | 669 / 8 | -0.022 | 0.061 | 1.000 |
| return_5_reversal | 5 | 212 / 9 | -0.033 | 0.103 | 1.000 |
| return_5_reversal | 15 | 83 / 12 | 1.008 | 0.774 | 1.000 |

Positive signed midpoint return is not executable profit. No trade is represented by zero signal. Signals do not overlap within a rule/horizon. Missing exit labels remain in the ledger. A two/five-bps sensitivity is available in results.json, but does not replace actual option quote replay.

RSI uses Wilder-style exponential smoothing, 14 minutes, levels 30 and 70. Bollinger uses a 20-minute mean and population standard deviation, two standard deviations. EMA spans are 8 and 21. Donchian uses prior 20 completed minutes. Opening range needs all first 15 regular-session minutes, and becomes usable only afterward. Five-minute reversal requires a two-bps preceding move.

## Sources

[TA repository](https://github.com/bukosabino/ta) and [indicator source](https://github.com/bukosabino/ta/blob/master/ta/volatility.py) were inspected for definitions. This study implements small formulas locally; it does not run untrusted repository code or claim exact library parity.

[Lo, Mamaysky and Wang](https://www.nber.org/papers/w7613) motivate objective pattern definitions. This is not a replication of their daily US-stock kernel study.

[Bailey et al.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659) motivate preserving all trials. Holm correction covers these 18 hypotheses only, not every experiment in the wider programme.

Run `python research/05_indicator_patterns/study.py` from nifty-research.

## Review correction, 2 October 2026

EMA and RSI now restart their exponential histories after every incomplete or missing minute. A rolling validity mask alone did not remove pre-gap smoothing state. Opening-range signals now also require a complete current minute. The already observed opening range remains usable after a later gap within the same recording segment; a recorder restart still invalidates that segment's opening range.

Pre-correction code, results and ledger remain under artifacts/revisions/pre-gap-fix. The correction changes evidence reconstruction, not indicator thresholds or the registered 18 trials.
