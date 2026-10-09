# Short-horizon mean reversion

This track tests whether large local price deviations followed by a one-minute turn recover enough to pay the recorded cash-equity trading costs. It is an offline research experiment. The three rules below were frozen before their first replay on October 1, 2026. No threshold is chosen from validation or audit P&L.

Run from the repository root with `python -m research.03_mean_reversion.run`. Run focused behavior checks with `python -m unittest discover -s research/03_mean_reversion/tests -v`.

## Frozen hypotheses

All bars use received bid/ask midpoints. A bar becomes available at the first observation in the following minute. Require at least 10 observations, a first observation within 10 seconds of the minute start, and a final observation within its last 10 seconds. An unusable quote or gap over 15 seconds clears history. This does not reconstruct exchange ticks or trade OHLC.

| Rule | Entry decision |
| --- | --- |
| Rolling z-score fade | Compute mean and population standard deviation of the 20 completed bars before the signal bar. Fade a signal-bar deviation of at least 2 standard deviations and 15 to 120 bps, only after a 1 bps turn toward the mean. Require prior-window standard deviation of at least 2 bps. |
| VWAP deviation turn | Fade a completed bar 25 to 120 bps away from its recorded VWAP, after a 1 bps turn. Unknown VWAP refuses entry. Require 21 completed bars but do not assume VWAP is a stationary mean. |
| OU admissible fade | Fit an intercept and AR coefficient to the prior 20 completed prices. Admit only `0 < phi < 1`, a fitted half-life of 2 to 15 bars, and fitted equilibrium within 100 bps of the sample mean. Then apply the 2-sigma, 15-to-120-bps fade and 1 bps turn. |

All use a 30 bps target, 20 bps stop, 600-second time exit and cooldown, 5 bps maximum spread, 5-second strict trade freshness, and the common account/execution model. The common fee reserve applies before admission. These numbers are hypotheses, not estimated optimal stopping boundaries.

For the OU diagnostic, `phi = cov(x[t], x[t+1]) / var(x[t])`, `mu = intercept / (1 - phi)`, and `half_life = -ln(2) / ln(phi)`. A short rolling fit can falsely imply mean reversion. It does not establish stationarity, and a local cash-equity price is different from the pair spread assumed by the source paper. No continuous-time stopping PDE is implemented.

## Sources and transfer limits

- [Leung and Li, optimal mean-reversion trading with costs and stop loss](https://arxiv.org/abs/1411.5062). This paper studies a mean-reverting spread and cost-dependent entry/exit timing. It motivates testing bounded deviations and costs together. Our local-price AR fit is a screening adaptation, not a reproduction of its optimal strategy.
- [Dai, Medhat, Novy-Marx and Rizova, reversals and liquidity provision](https://www.nber.org/papers/w30917). The research links reversal speed and persistence to different liquidity measures. We do not infer that a daily or cross-market finding proves one-minute NSE reversal profits.
- [Nagel, evaporating liquidity](https://www.nber.org/papers/w17653.pdf). This paper motivates viewing reversal returns as compensation for liquidity provision. Our executions cross the spread and model neither passive queue priority nor dealer inventory.
- [Hudson and Thames, ArbitrageLab official repository](https://github.com/hudson-and-thames/arbitragelab). This is a source to inspect for later paired-spread implementations. No package or remote executable was downloaded or used in this initial experiment.
- [ArbitrageLab OU model documentation](https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/optimal_mean_reversion/ou_model.html). The maintained example separates model fitting from out-of-sample entry/exit levels and checks fit against simulation. Its documented daily/monthly/yearly frequency interface does not directly establish minute-scale calibration. We use a local discrete AR diagnostic instead of silently treating a minute as a trading day.

## Evaluation boundaries

Use August 18 top-12 ADV universe. Development sessions are August 19, 20 and 21. Validation-labelled sessions are August 24 and 25. August 31 and September 1 are historical audit sessions. These dates have already been observed in earlier work; none is a pristine holdout. Preserve every frozen variant result, including losing and zero-trade cases.

Strict mode rejects missing freshness flags and old/unknown trade age. Receipt-proxy mode is a deliberately unverified sensitivity that keeps unknown metadata visible. Trade age is not source quote age; neither mode establishes quote latency. One-observation-per-second recording cannot prove scalping fill quality. Every result has promotion disabled.
