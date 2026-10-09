# Indicators and completed quote patterns

This track tests three explicit trading rules, including a continuation rule and two reversal rules. Source indicator definitions supply formulas, not profit claims. The variants were frozen before their first replay on October 1, 2026. Every variant uses the same account, fees and exits as the mean-reversion track so the indicator definition is the changed variable.

Run from the repository root with `python -m research.07_indicator_patterns.run`. Run focused checks with `python -m unittest discover -s research/07_indicator_patterns/tests -v`.

## Frozen hypotheses

| Rule | Entry decision |
| --- | --- |
| Wilder RSI recross | Calculate 14-bar RSI with an initial arithmetic gain/loss average and Wilder recursive smoothing. Buy when completed-bar RSI crosses up through 30, sell when it crosses down through 70. Flat prices use a documented neutral value of 50. |
| Bollinger breakout | Build a mean and population standard deviation from the 20 bars preceding the signal bar. Enter in the direction of a first crossing outside the 2-sigma envelope with at least 3 bps one-bar movement. Require at least 2 bps prior standard deviation. |
| Wick rejection | Require a completed bar range of at least 10 bps, a rejection wick of at least 60% of range, body at most 25% of range, and close in the opposing 25% edge. The rejected extreme must exceed the prior 5-bar extreme. Buy lower rejections and sell upper rejections. |

All require 21 completed midpoint bars. A bar releases at a later minute's first quote; same-bar orders never fill. Require at least 10 observed quotes and coverage within 10 seconds of both minute edges. A gap over 15 seconds or unusable quote resets history and RSI. OHLC means observed quote-midpoint extremes, not all traded extremes. The wick heuristic is explicit and does not reproduce TA-Lib candle settings.

All use a 30 bps target, 20 bps stop, 600-second time exit and cooldown, 5 bps maximum spread, 5-second strict trade freshness and the common cost-reserve gate. Bollinger thresholds deliberately use the preceding window. Source libraries often include the current close in the displayed band. We distinguish that convention rather than imply numerical equivalence.

For RSI, positive and negative close increments seed separate 14-increment arithmetic averages. Each subsequent average is `(13 * old_average + new_increment) / 14`. RSI is `100 * average_gain / (average_gain + average_loss)`. For Bollinger rules, `upper/lower = prior_mean +/- 2 * prior_population_std`.

## Primary sources and repository review

- [TA-Lib official RSI formula and implementation links](https://github.com/TA-Lib/ta-lib/blob/main/ta_codegen/input/rsi/rsi.md). Supplies the Wilder smoothing convention. We implement the formula locally and test its seed and recursive update. Flat-price neutrality is our explicit convention.
- [TA-Lib official Bollinger definition](https://github.com/TA-Lib/ta-lib/blob/main/ta_codegen/input/bbands/bbands.md). Supplies the mean-plus-standard-deviation construction. Our prior-window breakout rule is a research hypothesis layered on that construction.
- [TA-Lib official supported functions](https://github.com/TA-Lib/ta-lib-python/blob/master/docs/funcs.md). The repository provides indicator and candle recognizers. Recognizer availability provides no evidence of executable net returns. No code was downloaded or executed from the repository.
- [Lo, Mamaysky and Wang, foundations of technical analysis](https://www.nber.org/papers/w7613). This research makes pattern recognition systematic and studies conditional daily returns. Our simple one-minute quote-pattern rule uses neither their kernel algorithm nor their sample and is not a replication.

## Evidence limits

Use the prior August 18 ADV universe and the shared seven-session development/validation/historical audit split. Earlier work already observed these recordings. Broad indicator searches increase false discoveries, so all variants remain in the ledger and no winner gets promoted from this small sample. No neural model, fitted hyperparameter or pattern selection uses validation outcomes.

Unknown freshness flags and trade age block strict mode. Receipt-proxy sensitivity can show whether a rule has any recorded-price behavior but cannot establish fresh exchange quotes or live profits. Source quote age, true volume bars, queue position, complete trade extremes and impact are unavailable. The common next-observation model crosses quotes and keeps unresolved positions explicit.
