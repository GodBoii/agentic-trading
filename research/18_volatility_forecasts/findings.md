# Variance forecast findings

October 1, 2026. Completed the fixed EWMA versus rolling-variance study. It yields 12,004 identical receipt-proxy forecast/outcome pairs per model. Differences are small and change with the loss measure and chronological group. No trading edge is claimed.

## What ran and passed

Seven sessions, two quality modes and three models produce fourteen quality/forecast passes and 42 model/session metric sets. Every pass uses the fixed twelve-stock August 18 ADV universe. All models use the same completed-minute log midpoint returns, thirty-return warmup, positive forecast floor of 1e-12 and eligibility rules. Lambdas 0.94 and 0.97 were not fitted or selected after results.

Twelve behavioral and formula tests pass. They verify EWMA recursion, common warmup seeds, divergent later updates, next-minute causality, unchanged earlier forecasts when future prices change, zero returns, positive floors, missing-minute resets, invalid bars, partial bars, receipt gaps and instrument identity. Compilation passes. Saved source hashes, all seven tape hashes, pair-file hashes and every forecast/outcome timestamp relationship pass in `runs/initial-v1/verification.json`.

Strict mode has fifty valid minute bars in total but no thirty-return-contiguous forecast/outcome pairs. Its loss estimates are unavailable, not zero. Receipt-proxy mode has 25,454 valid bars and 12,004 paired next-minute outcomes. Of those outcomes, 1,281 have zero log return. Zero outcomes remain in the evaluation without adding an artificial target floor.

| Date | Strict pairs | Receipt-proxy pairs |
| --- | ---: | ---: |
| August 19 | 0 | 1,483 |
| August 20 | 0 | 2,045 |
| August 21 | 0 | 2,731 |
| August 24 | 0 | 666 |
| August 25 | 0 | 1,466 |
| August 31 | 0 | 941 |
| September 1 | 0 | 2,672 |

These are repeated stocks and minutes within seven days, not 12,004 independent market regimes. Strict quality and continuous warmup leave no useful sample here. Receipt-proxy estimates remain conditional on unverified quote usability.

## Forecast loss results

MSE below is in decimal log-return fourth-power units, multiplied by 1e12 for readable values. Gaussian QLIKE is log of forecast variance plus outcome squared return divided by forecast variance. It can be negative in these units. Lower values are better for both measures.

| Model | Pairs | MSE times 1e12 | Mean Gaussian QLIKE |
| --- | ---: | ---: | ---: |
| EWMA 0.94 | 12,004 | 3.513272 | -14.274543 |
| EWMA 0.97 | 12,004 | 3.516815 | -14.304303 |
| Rolling thirty returns | 12,004 | 3.538314 | -14.187994 |

The 0.94 model has the smallest pooled MSE, about 0.71% below rolling thirty. The 0.97 model has the lowest pooled QLIKE. These small descriptive differences do not establish statistical superiority or justify replacing a live risk model.

| Group | Model | Pairs | MSE times 1e12 | QLIKE |
| --- | --- | ---: | ---: | ---: |
| Development | EWMA 0.94 | 6,259 | 1.417231 | -14.576427 |
| Development | EWMA 0.97 | 6,259 | 1.416804 | -14.573407 |
| Development | Rolling thirty | 6,259 | 1.429123 | -14.545633 |
| Diagnostic validation | EWMA 0.94 | 2,132 | 1.584988 | -14.130517 |
| Diagnostic validation | EWMA 0.97 | 2,132 | 1.630751 | -14.167552 |
| Diagnostic validation | Rolling thirty | 2,132 | 1.569415 | -13.942882 |
| Historical audit | EWMA 0.94 | 3,613 | 8.282223 | -13.836561 |
| Historical audit | EWMA 0.97 | 3,613 | 8.267729 | -13.918814 |
| Historical audit | Rolling thirty | 3,613 | 8.354014 | -13.713076 |

Rolling thirty has lower MSE than both EWMA models on diagnostic validation. The ranking also differs between MSE and QLIKE in development. Larger historical-audit MSE shows the evaluation's sensitivity to that interval's realized movements; it does not by itself identify a change in latent volatility process.

## Interpretation and source limits

The [official RiskMetrics archive's indexed excerpt](https://www.msci.com/documents/10199/5915b101-4206-4ba0-aee2-3449d5c7e95a) specifies 0.94 daily and 0.97 monthly decays. Using them on minute returns is a predeclared adaptation. Direct PDF retrieval timed out, so we do not claim to reproduce its full methodology.

[Patton's paper](https://public.econ.duke.edu/~ap172/Patton_vol_proxies_JoE_2011.pdf) explains comparing variance forecasts through imperfect proxies. The zero-mean and measurement assumptions matter. This tape's quote age and event completeness are unverified, so squared received-midpoint returns are not proven unbiased observations of latent conditional variance.

Forecasts use only receipts before the minute boundary. The offline calculation assumes a local timer can finalize that close; actual scheduler and processing latency are unmeasured. Minute grouping cannot establish HFT timing, and lower variance forecast loss predicts neither price direction nor profitable fills. No return, Sharpe ratio or risk-management benefit follows directly from these metrics.

## Checkpoint and next data

Preserve this completed study as `runs/initial-v1`. The directory contains the frozen plan, saved Python source, fourteen summaries, fourteen paired forecast/outcome files, manifests, aggregate results and hash/timing verification. There are no account trades or unresolved positions because the study never creates exposure.

Next evaluate the same frozen models on new timing-verified sessions and assess calibration by independently defined volatility buckets. If forecasts later inform sizing or stops, run a separate account experiment with costs, risk constraints and execution effects. Do not select a decay from these seven dates and call it a validated trading model.
