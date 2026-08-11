# Stage 2 setup-quality research and backtest

## Decision

The new research layer is working, leakage-safe, and useful for diagnosing Stage 2. The tested `quality_v3` rule is **not approved for automatic trading or agent dispatch**.

It reduced the number of events and improved execution quality, but it failed the untouched August 4 holdout. All tested exit profiles remained negative after conservative costs. The correct operational state is therefore shadow collection and research only.

## What was implemented

`pipeline/research/stage2_quality_replay.py` reads the persisted Stage 2 event file and one-second Parquet tape without modifying either. It reconstructs one-minute candles and calculates:

- EMA 9 and EMA 21.
- RSI 14.
- ATR 14.
- Session VWAP and VWAP slope.
- Five-minute directional movement and ten-minute trend efficiency.
- Minute volume ratio, relative volume, and volume acceleration.
- Candle body, close location, upper/lower wick, doji, and bullish/bearish engulfing patterns.
- Distance from the ORB or VWAP trigger in ATR units.
- Distance to recent intraday high/low structure as a simple resistance/support proxy.
- Sixty-second average depth imbalance and directional persistence.
- Current five-level quantity and order-count imbalance.
- Spread and estimated slippage.

The replay evaluates the event at its saved event time. Candle and indicator features come from the previous fully completed one-minute candle. Live order-book features include only observations at or before the simulated entry. Future prices are used only after the decision is frozen, to label the result.

`pipeline/runtime/run_stage2_quality_backtest.py` creates:

- A machine-readable summary.
- Every evaluated candidate and gate decision.
- Current-versus-improved comparisons.
- Score-calibration charts.
- Six predeclared exit-profile comparisons.
- An input manifest containing the path, size, and modification time of every source file.

The run aborts if any source input changes while the replay is running.

## Data separation

The dates were separated before final evaluation:

| Role | Date | Important limitation |
|---|---|---|
| Development | 2026-07-31 | Recording starts late, around 10:13 IST |
| Validation | 2026-08-03 | Broad session coverage |
| Untouched holdout | 2026-08-04 | Partial session ending around 13:24 IST |

The August 4 outcomes were not inspected until the `quality_v3` score, threshold, hard gates, and cooldowns had been frozen. A zero-ATR software edge case stopped the first holdout attempt before any result was produced. The positive ATR floor was then fixed and regression-tested without changing the trading rules.

## Tested quality-v3 hypothesis

The first scoring attempts assumed that stronger same-direction momentum, higher RVOL, and stronger same-direction depth should receive more points. The development replay showed that this frequently rewards an already crowded or extended move.

Version 3 instead prefers:

- A price still close to the ORB/VWAP trigger rather than far beyond it.
- A fresh turn after a controlled pullback rather than a long same-direction chase.
- Moderate relative volume and acceleration rather than extreme crowding.
- Moderate, persistent order-book support rather than a single extreme depth snapshot.
- A tight spread and low estimated slippage.
- A supportive previous closed candle, while treating candle patterns as evidence rather than predictions.

Hard gates require a score of at least 65, spread no greater than 0.04%, estimated slippage no greater than 0.04%, and trigger extension no greater than 0.40 ATR. A 45-minute same-setup cooldown and a 10-minute per-stock cooldown suppress repeated signals.

## Results

The primary directional label uses a 0.20% target, 0.20% stop, and five-minute horizon.

| Date | Model | Signals | Resolved win rate | Mean gross return | Conservative mean net return |
|---|---:|---:|---:|---:|---:|
| 2026-07-31 | Current raw | 1,125 | 45.69% | -0.01504% | -0.13699% |
| 2026-07-31 | Quality v3 | 33 | 50.00% | +0.00959% | -0.05057% |
| 2026-08-03 | Current raw | 2,211 | 45.97% | -0.01383% | -0.14995% |
| 2026-08-03 | Quality v3 | 79 | 66.67% | +0.02469% | -0.04526% |
| 2026-08-04 holdout | Current raw | 2,119 | 45.81% | -0.01523% | -0.14595% |
| 2026-08-04 holdout | Quality v3 | 106 | 47.62% | -0.01258% | -0.07542% |

The holdout is decisive: the development improvement did not generalize. Version 3 lowers estimated cost and adverse excursion but does not reliably predict the next move.

Six exit profiles were declared before opening the holdout. They covered 0.15%-0.40% targets, 0.10%-0.20% stops, and five-to-fifteen-minute horizons. Every version-3 profile was negative on the holdout before and after costs. Changing the stop, target, or horizon therefore does not rescue the current setup selector.

## What the result means

EMA, RSI, VWAP, candle patterns, support/resistance, volume, and five-level depth describe current and past market state. They do not automatically reveal bank, operator, hedge-fund, or investor positions, and displayed depth cannot identify the owner or prove intent. Large displayed orders can also be cancelled.

The recorded data can support evidence such as absorption, repeated replenishment, failed breakouts, depth persistence, and liquidity sweeps. Those behaviours must be defined as time sequences and validated across many independent sessions. A single imbalance snapshot or one candle name is not enough.

## Safe next step

Keep Intra-Finder in shadow mode and collect at least 20 complete, stable trading sessions. Preserve market-open coverage and avoid backend restarts. The next research version should be specified before viewing its holdout days and should add:

1. Market-relative strength versus NIFTY and the stock's sector over matching time windows.
2. True retest/acceptance logic around ORB, VWAP, and repeatedly tested intraday levels.
3. Order-flow sequences: replenishment, absorption, cancellation/churn, and sweep recovery—not isolated depth imbalance.
4. Market-regime stratification for research, while keeping regime as context for the agent.
5. Walk-forward testing by day, with several untouched days and minimum sample requirements.
6. Execution calibration using actual order fills or broker-confirmed cost assumptions.

Automatic agent triggering should be considered only after multiple untouched days show positive conservative net expectancy, stable results across market conditions, acceptable drawdown, and enough signals for the estimate to be credible.

## Trade-readiness v1 audit after the August 10 agent review

The August 10 agent reports showed that most skips came from poor entry location, insufficient room, missing confirmation, stale trading and conflicting structure. Stage 2 now treats raw indicators as observations and applies a separate trade-readiness layer before agent dispatch. The implementation includes:

- Five- and fifteen-minute structure instead of one-minute direction alone.
- ATR-normalized support/resistance location and target room.
- Five-minute confirmation and a minimum five-minute observation window.
- Time-of-day RVOL, volume acceleration and recent five-minute participation.
- Exchange last-trade freshness and persistent 30-second depth measurements.
- Low candle-pattern weights and no dispatch for doji/volume-only observations.
- Rejection of conflicting transitions, recent two-sided price action and excessive signal churn.
- A bounded downstream AI queue and worker-start expiration.

The scoring and gates were frozen before replaying the older dates below. Source Parquet files were read without modification. The recorded windows were measured from the data rather than inferred from folder names.

| Date | Recorded IST window | Readiness events | 15m median directional return | 30m median | 60m median |
|---|---|---:|---:|---:|---:|
| 2026-07-31 | 10:13-15:30 | 59 | 0.0000% | -0.0326% | -0.0745% (49 eligible) |
| 2026-08-03 | 09:20-15:02 | 112 | -0.0402% (111 eligible) | -0.0403% (105) | -0.1062% (101) |
| 2026-08-04 | 09:29-13:24 | 89 | -0.0172% (83) | -0.0432% (76) | +0.0560% (64) |
| 2026-08-10 | 12:50-14:01 | 17 | +0.0600% (only 6 eligible) | insufficient follow-up | insufficient follow-up |

Across July 31, August 3 and August 4, the weighted mean directional return was approximately -0.017% at 15 minutes, -0.027% at 30 minutes and -0.015% at 60 minutes before costs. Approximately 45%, 42% and 44% of eligible events were positive at those horizons. These results do not demonstrate predictive edge.

The wider symmetric target/stop audit was also inconsistent. At 1.0% over the available next hour, July 31 produced 14 target-first versus 6 stop-first outcomes, August 3 produced 10 versus 17, and August 4 produced 8 versus 8. This variation across days is exactly why one favourable session cannot be used to approve live routing.

The readiness layer is therefore approved only as a **shadow-mode traffic and explanation layer**. It materially reduces agent demand, records explicit reasons for suppression, and prevents stale backlogs, but it is not approved as evidence that the remaining setups are profitable. `INTRA_FINDER_SHADOW_MODE=1` and `EXECUTIONER_ALLOW_LIVE_ORDERS=0` remain the required settings.

## Commands

From `python-backend`:

```powershell
python -m unittest tests.test_stage2_quality_replay -v
python -m pipeline.runtime.run_stage2_quality_backtest --dates 2026-07-31 2026-08-03 --output results/research/stage2-quality-v3-devval --rebuild-features
python -m pipeline.runtime.run_stage2_quality_backtest --dates 2026-08-04 --output results/research/stage2-quality-v3-holdout --rebuild-features
```
