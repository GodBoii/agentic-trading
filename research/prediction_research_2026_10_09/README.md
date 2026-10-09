# GitHub, papers and weighted trading predictions

Completed October 9, 2026, using three research subagents and a coordinating daily-history study. No method established a useful live trading edge. Combining signals sometimes reduced activity or forecast error, but the measured improvements did not establish better tradable predictions.

## What the earlier research combined

Earlier work did combine information. Opening-range breakouts had VWAP/direction confirmations. VWAP continuation used impulse, pullback and recovery states. Joint ridge/logistic models learned coefficients on momentum, VWAP distance, depth imbalance and spread, and one rule required both a net-return forecast and profit-probability gate. Gaussian-mixture responsibilities conditioned continuation or fading.

Those experiments differ from comparing independent strategy forecasts with learned ensemble weights. Regime responsibility also is not a calibrated probability that a trade will win. This batch adds direct standalone-versus-combination comparisons, rather than assuming more confirmations or larger weights improve accuracy.

## Completed experiments

| Study | New comparison | Executed evidence | Conclusion |
|---|---|---|---|
| [41, supplied SSRN paper](../41_ssrn_4631351/README.md) | Paper-style VWAP direction versus VWAP plus momentum/path confirmation | Six predefined stocks, 5,784 complete instrument-days on 1,201 dates, two rules and three cost scenarios. Separate 28 common-engine quote replays. | Both candle rules lost heavily. The confirmation filter exited to cash more often and increased turnover. No exact QQQ/TQQQ replication claim. |
| [42, weighted forecast ensemble](../42_weighted_ensemble/README.md) | Momentum, VWAP, depth and spread specialists; joint ridge; equal average; learned convex average | 56 common-engine replays on four later dates; 12,248 fitted receipt-proxy forecast rows. Supplemental row ledgers reconstruct frozen forecasts without refitting. | Tiny error gain over the best specialist, worse preferred-side accuracy, no prediction passed the 2 bps net-entry gate. |
| [43, GitHub-derived signal mechanisms](../43_github_methods/README.md) | Causal Kalman trend, CUSUM continuation, same-direction agreement | 42 common-engine replays across seven quote sessions | Agreement lost less in total by taking fewer trades. Its per-trade loss and net win rate worsened. |
| [44, longer daily stock histories](../44_daily_forecasts/README.md) | Momentum/reversal ridge, joint ridge, shallow random forest, equal/weighted blend, training-mean control | 19,089 training rows, 3,465 separate weight-fitting rows, 2,709 evaluation rows on 387 dates | Ensemble accuracy and RMSE were slightly worse than momentum alone. Learned weights were almost equal. Sparse bar-price sensitivities are not executable account results. |

These studies added 12 common-engine variants and 126 policy/session replays. The candle experiment separately produced 34,704 instrument-day ledger rows and 126,515 simulated round trips across repeated rules/cost scenarios. Those are not independent observations, and their totals must not be combined with the common-engine count. Daily forecasting is another separate diagnostic.

## How weighting was tested

A meaningful combination blends forecasts in comparable units, such as expected net basis points. Adding raw RSI, rupee prices and depth quantities with arbitrary weights does not produce a probability.

Track 42 fits each specialist on August 19-20 and estimates nonnegative, sum-to-one weights using predictions on August 21. Its objective is mean squared long/short net-return error plus a fixed penalty toward equal weights. It evaluates only August 24, 25, 31 and September 1 without refitting. Track 44 separately fits daily models through 2022, estimates inverse-error weights on 2023-2024 and evaluates 2025 through the available July 24, 2026 data.

The short-horizon learned weights were 85.67% spread, 14.33% depth and zero momentum/VWAP. This mainly improved cost estimation. It does not mean spread predicts direction with 85.67% accuracy. Specialist forecast errors had correlations of 0.989-0.999, so the inputs supplied little independent diversification.

| Short-horizon result, identical complete-label cohort | Value |
|---|---:|
| Spread specialist net-return RMSE | 6.745230 bps |
| Learned ensemble net-return RMSE | 6.745060 bps |
| Equal ensemble net-return RMSE | 6.762871 bps |
| Learned ensemble preferred-side accuracy | 46.24% |
| Always-long preferred-side control | 53.76% |
| Trades admitted by every tested forecast policy | 0 |

Preferred-side accuracy asks which realized long/short cost-adjusted label was larger. It is neither profitable-trade frequency nor a calibrated win probability. A forecast can slightly improve error while making worse directional choices. All predicted net edges remained below the frozen entry threshold.

On longer daily history, momentum direction accuracy was 52.78%, the learned ensemble 52.59% and the training-mean direction control 52.48%. Momentum RMSE was 122.422533 bps versus 122.463463 for the blend. Descriptive five-date block intervals for paired error differences included zero. The equal and weighted blends admitted the same two idealized positions; their total changed from +Rs67.16 at 2 bps per leg to -Rs52.17 at 5 bps. Two positions do not establish profitability.

## What was found in GitHub source

These are inspections of specific source files. Repository popularity does not verify returns. No downloaded repository was installed or executed.

| Repository | Actual formula or method inspected | Tested locally in this batch? |
|---|---|---|
| [Microsoft Qlib](https://github.com/microsoft/qlib) | Alpha158 candle/rolling factors, including body, range position and price/volume relationships. AverageEnsemble standardizes outputs per date and averages. DoubleEnsemble reweights samples, selects features and combines submodels. | Independently implemented a simpler equal/convex forecast blend. No Alpha158 or DoubleEnsemble training, and no claim of exact Qlib replication. |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | KAMA adapts its smoothing rate using path efficiency, then updates the moving average toward current price. | Source review only for KAMA. Efficiency confirmation was independently specified in the VWAP extension. |
| [mlfinpy](https://github.com/baobach/mlfinpy) | Symmetric CUSUM accumulates positive/negative log returns and emits an event after a strict threshold crossing, resetting the triggered side. | Yes, fixed event direction converted to a continuation rule and combined with Kalman. The event filter itself does not promise price predictability. |
| [pykalman](https://github.com/pykalman/pykalman) | Forward state prediction, covariance prediction and innovation-weighted correction. | Yes, independently coded local-linear price/slope filtering. No future smoothing or EM calibration. Covariance is conditional on model assumptions, not profit odds. |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | Portfolio environment, continuous actions converted to shares, cost deductions and reward based on asset-value change. | Reviewed environment only. No reinforcement-learning agent trained. |
| [skforecast](https://github.com/skforecast/skforecast) | Lag/window features and recursive forecasts that feed predictions into later forecast steps. | Source review only. Persistence can look good on price levels while providing no return edge. |
| [gabbocg/rz2013](https://github.com/gabbocg/rz2013) | Arithmetic forecast pooling and inverse discounted historical squared-error weighting, with expanding predictive regressions. | Static calibration-only inverse-MSE adaptation on local daily returns. No macroeconomic-data replication or future/full-sample coefficient selection. |
| [mlfinlab public CUSUM source](https://github.com/hudson-and-thames/mlfinlab) | The inspected public functions were docstrings followed by `pass`. | No executable implementation inferred from a stub. Actual recursion came from the separate mlfinpy source. |

Pinned commit/file hashes and the exact source links are in each track's sources.md and manifests. The complete Qlib factor/model libraries and the broader RL/neural systems were not benchmarked here.

## What the papers contributed

The supplied [SSRN 4631351 PDF](../ssrn-4631351.pdf) was read in full, including its 26 pages and method examples. It computes `VWAP_t = sum(TP_i * volume_i) / sum(volume_i)`, with `TP_i = (high_i + low_i + close_i)/3`, reset each session. Completed close above VWAP means long and below means short; a later completed crossing reverses direction. Its volume weights construct an average price, not an ensemble forecast.

The original US ETF study assumes zero slippage and a USD0.0005/share commission. Our six-stock NSE adaptation uses the saved local candles, integer shares, current frozen Indian cash fees and predeclared adverse slippage. At the primary 1 bps per-leg assumption, the baseline lost Rs593,446.38 and the confirmed rule Rs593,517.85 from Rs600,000 starting across six independent compounded sleeves. Both had negative gross PnL before fees. The later period carries depleted capital, so inactivity there cannot count as accurate abstention. These results do not reproduce or disprove the original QQQ/TQQQ results. [Original paper record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351).

[Gu, Kelly and Xiu](https://academic.oup.com/rfs/article/33/5/2223/5758276), also on [SSRN 3306110](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3306110), provided the original chronological split, regularization and tree-interaction methodology. The relevant original sections were inspected. The local random forest tests a much smaller technical-feature problem, rather than their monthly US asset-pricing design.

[Rapach, Strauss and Zhou, SSRN 1257858](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1257858) supplied forecast-combination motivation. Its indexed original combination section and the R replication source distinguish ex ante weights from hindsight selection. The local static inverse-error rule differs from recursive macro forecasts. The [2023 Rapach/Zhou survey](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4403635) was available at abstract level only. [DoubleEnsemble](https://arxiv.org/abs/2010.01265) and its Qlib source were reviewed as a more complex candidate; full DoubleEnsemble was not trained.

The SSRN landing page and several direct paper pages returned fetch errors. Accessible primary copies, indexed original material and the supplied local PDF were used with those access limits recorded. No statement here implies that all SSRN research or every listed paper was reproduced.

## Data and verification

The broader inventory found 2,965 NSE daily-history files and 327 yearly minute files. The complete minute audit checked 21,723,341 rows, identifying 43,882 complete valid instrument-days across 73 stocks. Only the six predefined names were backtested in the candle study. The earlier 12-stock quote cohort has no stored minute folders, so the two cohorts must remain separate.

All 215 research tests passed with pytest importlib mode. This includes the earlier 174 and 41 new checks. Compilation passed. Independent review reproduced all 2,709 daily forecasts from frozen JSON state and checked actual-data prefix causality. A separate check verified all 126 new common-engine replays, all 126,515 candle trade fee calculations, 34,704 daily ledger rows, 35 candle input files and seven daily input files. See verification.json.

One strict quote run retains two unresolved positions on August 21 with very old final usable quotes. Its closed-trade totals exclude those positions and are not a complete account result. Strict ensemble fitting lacks eligible training data. Receipt-proxy results assume usable source quotes that the recordings do not verify.

Additional limits include current-survivor samples, ex-post complete-day filtering, unknown corporate-action/candle-label provenance, and reference candle prices without measured spread or capacity. A passing arithmetic check cannot establish executable fills. Older quote dates were previously inspected; the new daily split is chronological without a broader pristine-holdout claim. No live settings or broker orders changed.

## Research decision

Keep the single-model and simple-mean controls. The tested blends have not earned additional complexity or live promotion. The useful next comparison requires a predefined broader cohort, verified timestamps and bid/ask capacity, with fresh dates reserved before model selection. More independent predictors could include genuine transaction flow, market/sector returns and synchronized cross-instrument data; repeating many correlated price indicators is unlikely to supply the missing information by itself.

If testing new weighting methods, record every trial, train weights on chronological out-of-sample base forecasts, report paired error and direction benchmarks, and evaluate net returns under an executable account model. Do not lower these frozen gates or restart depleted sleeves after seeing results and call that independent validation.

## Reproduce

Each track's README contains its frozen run commands and output layout. Preserve existing run directories. Main verification:

```powershell
python -m pytest --import-mode=importlib research/41_ssrn_4631351/tests research/42_weighted_ensemble/tests research/43_github_methods/test_strategy.py research/44_daily_forecasts/tests -q
python -m research.prediction_research_2026_10_09.verify
```

The combined verifier preserves its existing report and requires a new output/report version for a repeat. Full local evidence remains beside each study; compact specifications, manifests, results and verification are versioned for review. Raw market files, full paper extraction, existing unrelated changes and credentials are excluded from publication.
