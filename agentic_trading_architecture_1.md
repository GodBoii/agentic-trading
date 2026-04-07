Your two-stage design is the right architecture for an agentic intraday system.  
For BSE-scale coverage, the key is: **Step 1 narrows the universe hard**, and **Step 2 does deep inference + strict risk gating**.

**1) Core Principle**
1. You should not try to “predict” all ~5000 stocks equally.
2. Build a funnel: `5000 -> 300 liquid -> 30 setups -> 1-3 executable trades`.
3. Most edge comes from:
`liquidity filtering + regime detection + risk control`, not just model complexity.

**2) Step 1: Stock Sorting Engine (continuous, higher-level loop)**
1. **Universe sanitation (daily pre-market + intraday refresh):**
`exclude illiquid, suspended, ASM/GSM, extremely wide spread, low float traps`.
2. **Tradability score (fast):**
compute per stock every N minutes:
`Tradability = w1*Liquidity + w2*VolatilityQuality + w3*SpreadQuality + w4*RelativeVolume + w5*MomentumState`
3. **Liquidity filter (hard gate):**
minimum median traded value, minimum volume, max spread %, minimum tick activity.
4. **Volatility-quality filter:**
prefer stocks with movement large enough for intraday edge, but not random whipsaw chaos.
5. **Relative activity detector:**
today’s volume vs rolling baseline; opening range expansion; abnormal participation.
6. **Regime-aware ranking:**
different ranking weights for `trend day`, `mean-revert day`, `event day`.
7. **Output contract for Step 2:**
store top K candidates + metadata:
`symbol, score, regime tag, liquidity stats, trigger states, timestamp`.
8. **Cadence:**
run every `5-15 min` during market hours, plus pre-open snapshot.

**3) Step 2: Deep Analysis + Trade Decision (user-triggered)**
1. **Input:** top symbol(s) from Step 1.
2. **Multi-model analysis stack:**
`Microstructure model` (spread, impact, short-term pressure),
`Technical state model` (trend strength, pullback quality, breakout probability),
`Volatility model` (expected move + stop distance),
`Regime compatibility model` (is this setup valid in current regime),
`Optional sentiment/news veto` (avoid high-risk headline traps).
3. **Ensemble decision:**
combine model outputs into:
`direction (long/short/none), confidence, expected reward:risk, invalidation level`.
4. **Trade policy layer (critical):**
no trade unless all pass:
`min confidence`, `min expected RR`, `max slippage`, `max spread`, `max correlation exposure`, `daily drawdown not breached`.
5. **Execution plan:**
`entry type, position size, stop, target(s), time stop, re-entry rules`.
6. **Agent action options:**
`Signal-only mode`, `Semi-auto confirm mode`, `Full-auto mode`.
7. **Exit intelligence:**
adaptive exit by volatility compression, structure break, or time decay.

**4) Risk Architecture (non-negotiable)**
1. Per-trade risk cap (example: `0.25%-0.75%` of equity).
2. Daily max loss and hard kill switch.
3. Max concurrent positions.
4. Correlation-aware exposure cap (avoid same-sector clustering).
5. Execution health checks: stale data, API lag, rejected order fallback.
6. “No trade” is a valid output.

**5) Why this two-step split works**
1. Step 1 is compute-efficient and always-on.
2. Step 2 is expensive and precision-focused.
3. User-triggered flow becomes fast because candidate context is precomputed.
4. You reduce decision latency at the moment user enables AI trading.

**6) Data + MLOps you’ll need**
1. Clean historical OHLCV + intraday bars + live ticks/quotes if possible.
2. Corporate action adjustments and symbol mapping consistency.
3. Feature store with strict timestamp integrity (no look-ahead bias).
4. Backtest engine with realistic frictions: slippage, fees, partial fills.
5. Walk-forward validation by market regime, not random split.
6. Paper-trading shadow mode before live deployment.

**7) Practical rollout plan**
1. **Phase 1:** rule-based sorter + rule-based execution (no ML yet).
2. **Phase 2:** add probabilistic scoring model in Step 2.
3. **Phase 3:** ensemble + adaptive position sizing.
4. **Phase 4:** online monitoring + periodic retraining + drift alerts.

**8) Metrics that actually matter**
1. Hit rate is secondary.
2. Track: `expectancy`, `profit factor`, `max drawdown`, `Sharpe/Sortino`, `slippage drift`, `latency-to-entry`, `regime-wise performance`.
3. Measure separately for Step 1 quality:
“how often top-ranked stocks became tradable opportunities.”

If you want, next I can turn this into a concrete **system blueprint**: service architecture, database schema, model interfaces, and exact pseudo-code for Step 1 and Step 2.