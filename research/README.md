# Trading research program

Independent research tracks share a fixed recorded-data cohort and consistent account/fee rules. Each completed track keeps its sources, frozen methods, code, tests, raw results and findings in its own folder.

The September30 baseline and architecture report are grouped in `intraday_lab`, the first track. Existing import paths and archived experiment evidence are preserved.

The first batch contains **39 frozen variants and 492 policy/session account replays**, excluding the first baseline, repeatability checks and separate paired/data diagnostics. These counts measure executed experiments, not independent samples or validated strategies.

The [October 9 GitHub, SSRN and weighted-prediction batch](prediction_research_2026_10_09/README.md) adds tracks 41-44, with **12 common-engine variants and 126 replays**, giving 51 variants and 618 initial common-engine replays across both batches. Its longer candle-rule and daily-history studies are separate diagnostics. That batch tested the supplied VWAP paper, equal/learned forecast blends, Kalman/CUSUM combinations and nonlinear daily models. No combination established a useful live edge.

No track is approved for live trading. Receipt-proxy results assume quote usability that our recordings do not verify. Strict results often have insufficient eligible observations. All historical dates were previously inspected, so none is a pristine final holdout.

The strict gate checks stored trade-age and health fields. It is not independent proof of quote freshness or correct historical decoder timezone semantics. Track15 investigates those timestamp assumptions.

## Research tracks

| ID | Topic | Status | Account replays |
|---|---|---|---:|
|01|[Deterministic momentum foundation](C:/Users/prajw/Downloads/Trader/research/intraday_lab/README.md)|foundation tested|0|
|02|[Opening-range breakout](C:/Users/prajw/Downloads/Trader/research/02_opening_range/README.md)|tested diagnostic|42|
|03|[Mean reversion](C:/Users/prajw/Downloads/Trader/research/03_mean_reversion/README.md)|tested diagnostic|42|
|04|[Order-book snapshot proxies](C:/Users/prajw/Downloads/Trader/research/04_microstructure/README.md)|tested diagnostic|42|
|05|[Cross-sectional relative movement](C:/Users/prajw/Downloads/Trader/research/05_relative_value/README.md)|tested diagnostic|42|
|06|[Volatility compression](C:/Users/prajw/Downloads/Trader/research/06_volatility_compression/README.md)|tested diagnostic|42|
|07|[Indicators and candle patterns](C:/Users/prajw/Downloads/Trader/research/07_indicator_patterns/README.md)|tested diagnostic|42|
|08|[Frozen numerical forecasting](C:/Users/prajw/Downloads/Trader/research/08_statistical_models/README.md)|tested diagnostic|24|
|09|[Variance-ratio regimes](C:/Users/prajw/Downloads/Trader/research/09_variance_ratio/README.md)|tested diagnostic|42|
|10|[VWAP pullback state machines](C:/Users/prajw/Downloads/Trader/research/10_vwap_pullback/README.md)|tested diagnostic|28|
|11|[Exit mathematics](C:/Users/prajw/Downloads/Trader/research/11_exit_math/README.md)|tested diagnostic|42|
|12|[Execution and cost sensitivities](C:/Users/prajw/Downloads/Trader/research/12_execution_costs/README.md)|tested diagnostic|56|
|13|[Fixed-pair spread models](C:/Users/prajw/Downloads/Trader/research/13_pairs_cointegration/README.md)|data/math diagnostic|0|
|14|[Intraday time-of-day information](C:/Users/prajw/Downloads/Trader/research/14_intraday_seasonality/README.md)|tested diagnostic|16|
|15|[Raw-packet timestamp integrity](C:/Users/prajw/Downloads/Trader/research/15_timestamp_integrity/README.md)|data/math diagnostic|0|
|16|[Relative-volume surprises](C:/Users/prajw/Downloads/Trader/research/16_relative_volume/README.md)|tested diagnostic|16|
|17|[Regime mixture models](C:/Users/prajw/Downloads/Trader/research/17_regime_mixtures/README.md)|tested diagnostic|16|
|18|[Realized volatility forecasting](C:/Users/prajw/Downloads/Trader/research/18_volatility_forecasts/README.md)|data/math diagnostic|0|
|19|Kalman state estimation|queued|0|
|20|CUSUM event detection|queued|0|
|21|Alternative event bars|queued|0|
|22|Price impact descriptors|queued|0|
|23|Post-fill adverse selection|queued|0|
|24|Passive queue models|queued|0|
|25|Participation and impact|queued|0|
|26|Cross-instrument lead and lag|queued|0|
|27|Opening-to-closing momentum|queued|0|
|28|News arrival filters|queued|0|
|29|Auction and gap mechanics|queued|0|
|30|ETF and constituent residuals|queued|0|
|31|Futures basis|queued|0|
|32|Options volatility surfaces|queued|0|
|33|Hedged volatility trading|queued|0|
|34|Tree model baselines|queued|0|
|35|Temporal neural networks|queued|0|
|36|Model calibration and abstention|queued|0|
|37|Reinforcement-learning simulation|queued|0|
|38|Latency and decay|queued|0|
|39|Fault and recovery experiments|queued|0|
|40|[Multiple-hypothesis audit](C:/Users/prajw/Downloads/Trader/research/40_multiple_testing/README.md)|data/math diagnostic|0|

Queued topics are plans, not completed research. New folders are created when implementation begins. Several require data that is not available in the current tapes.

## Reproduce and verify

From the repository root:

```powershell
python -m research.common.data
python -m research.common.verify_program --tests --output research/program/runs/new-verification
python -m research.program.build_index
```

The cache fixes the prior-Aug18 universe and fingerprints normalized observations. The verifier checks source/input fingerprints, expected session coverage, trade chronology, long/short P&L arithmetic, fees totals, slot bounds and unresolved exposure flags. A verified experiment can still lose money or be statistically uninformative.

Use each track's README to run a new experiment. Output folders must be new; interrupted or invalid runs are retained and excluded. Source snapshots document code used at the time. Do not replace a losing version with a profitable-looking version under the same name.

## Continuing research

Three subagents can work alongside the coordinator. Assign disjoint track folders and rotate topics as agents finish. Freeze methods before evaluation, add meaningful mathematical/causality tests, and report missing prerequisites. A tiny profitable result is a hypothesis requiring independent evidence.

The 40-topic queue sets scope for future batches. It does not schedule background execution. Research continues when this chat is running or through a separately configured automation.

Shared source is in `common`; baseline execution is in `intraday_lab`. Production code and broker orders are outside this program.
