# Deep Analysis of Current Trading System and Next-Phase Agent Plan

Date: 2026-04-28  
Workspace: `C:\Users\prajw\Downloads\Trader`

## 1. Scope of this analysis

This report is based on four kinds of evidence from the current system:

1. Runtime logs from [docker-logs.txt](C:/Users/prajw/Downloads/Trader/docker-logs.txt)
2. Persisted daily snapshots in `python-backend`
3. Current pipeline implementation under `python-backend/pipeline`
4. Existing architecture notes such as [agentic_trading_architecture.md](C:/Users/prajw/Downloads/Trader/agentic_trading_architecture.md)

The goal is not just to restate the intended design, but to compare:

- intended architecture
- implemented architecture
- actual runtime behavior today
- quality of the current system for intraday trading
- quality of the proposed next phase

## 2. Executive summary

The current system is a good early-stage pipeline architecture for narrowing a very large equity universe into a small intraday shortlist. It is much stronger as a discovery and filtering engine than as a complete autonomous trading system.

What is already good:

- clear staged separation between universe sanitation, momentum scan, monitor gate, and regime analysis
- persisted JSON outputs for each major stage, which improves debuggability
- practical use of rate limiting and retry handling around Dhan data access
- a regime lane that is not tightly entangled with stock selection logic
- monitor design that tries to wait for tick collector maturity instead of trusting cold live data immediately

What is not yet strong enough:

- orchestration is file-coupled and polling-based, so downstream components spend time waiting rather than reacting to events
- surveillance filtering is operationally weak today because ASM/GSM inputs appear empty
- stage naming and responsibility boundaries are slightly confusing, especially because the monitor stage still uses fields like `stage2_reason`
- no durable orchestration state, no message bus, and no formal decision trace across stages
- current monitor depends on tick counts, but the captured tick stats are still immature and do not yet look sufficient for final trade-quality filtering
- the system stops at shortlist and market context; it does not yet implement robust execution decisioning, portfolio-aware risk control, or post-trade feedback

Bottom line:

- as a stock discovery engine: promising
- as an intraday trade decision engine: incomplete
- as a production trading architecture: not yet production-grade
- as a foundation for the next multi-agent phase: viable, but only if the next phase is structured around deterministic data contracts and hard risk gates rather than free-form agent reasoning

## 3. What the current system actually is

The implemented system is best understood as four cooperating lanes:

1. Stage 1 universe sanitation
2. Stage 2 momentum ignition scan
3. Live monitor / liquidity gate
4. Market regime analyzer

These are orchestrated as separate runtime loops in:

- [run_sorting.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/runtime/run_sorting.py)
- [run_monitor_loop.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/runtime/run_monitor_loop.py)
- [run_regime_loop.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/runtime/run_regime_loop.py)
- [run_tick_collector.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/runtime/run_tick_collector.py)

The system uses JSON snapshots on local disk as the main coordination mechanism between lanes.

That means this is not a workflow engine in the strict sense. It is a file-based, eventually consistent pipeline.

That choice is acceptable for a prototype and even useful for debugging, but it has consequences:

- downstream stages poll for upstream outputs
- startup timing matters
- state freshness must be inferred from timestamps rather than enforced transactionally
- multiple services coordinate indirectly through files rather than through explicit events

## 4. Step-by-step analysis of the current sorting system

### 4.1 Stage 1: Universe sanitation

Implementation file:

- [stage1_sanitation.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/stage1_sanitation.py)

Configured filters:

- price: `100` to `3000`
- ADV20: at least `10 Cr`
- ATR percent: at least `1.5%`

Observed runtime on 2026-04-28:

- initial common BSE equities loaded: `5287`
- missing OHLC during prefilter: `781`
- price filtered out: `2478`
- remaining for historical scan: `2028`
- passed Stage 1: `165`
- pass rate: `8.4%`
- runtime: about `8.7 minutes`

Interpretation:

This is a sensible first stage for intraday trading because it aggressively shrinks the universe before expensive intraday work begins. The prefilter strategy is also reasonably efficient:

1. remove ASM/GSM names
2. bulk snapshot by price
3. fetch historical data only for survivors

That is a good architectural move because it minimizes expensive historical requests.

### 4.2 Stage 1 strengths

- good use of a fast bulk prefilter before deeper historical fetches
- clear logging of progress and failure reasons
- useful summary output saved locally
- practical features like rate-limit tracking and failure sampling

### 4.3 Stage 1 weaknesses

#### A. Surveillance filtering is likely not trustworthy today

Today’s local files:

- `List_of_GSM_Securities_28042026.CSV`
- `List_of_Long_Term_ASM_Securities_28042026.CSV`
- `List_of_Short_Term_ASM_Securities_28042026.CSV`

are zero-byte files, and logs show:

- `Loaded 0 GSM security ids`
- `Loaded 0 ASM security ids`

This means the system behaved as if there were no ASM/GSM exclusions today. For an intraday engine focused on safety and tradability, that is a meaningful operational weakness.

Even if the download step said "Downloaded", the functional result was empty.

Impact:

- Stage 1’s “safe tradable universe” guarantee is currently weaker than intended
- manipulated or surveillance-restricted names may leak into later stages
- this undermines trust in the sanitation layer

#### B. Stage 1 runtime is still heavy for same-day recovery

About `8.7 minutes` to rebuild the stage is acceptable once per day, but not ideal if:

- the container restarts late in the session
- the stage file gets corrupted or deleted
- you want fast recovery after transient failures

#### C. Too much dependency on repeated historical fetches

For a universe of 2028 stage-1 candidates, fetching each symbol’s historical data one by one is workable but still expensive and fragile under API variance.

### 4.4 Stage 1 evaluation

Scores:

- filtering logic quality: `7.5/10`
- operational robustness: `5.5/10`
- data-quality trustworthiness: `5/10`
- scalability for current universe size: `6.5/10`

Conclusion:

Stage 1 is conceptually sound, but today’s surveillance feed issue is a real flaw and should be treated as a first-class reliability problem.

## 5. Step-by-step analysis of the Stage 2 momentum scan

Implementation file:

- [stage2_momentum_ignition.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/stage2_momentum_ignition.py)

Configured filters:

- RVOL >= `1.3`
- price vs VWAP >= `0%`
- opening range breakout >= `0%`
- volume acceleration >= `1.1`

Observed runtime on 2026-04-28:

- input Stage 1 survivors: `165`
- fetch failures: `0`
- stage 2 passed: `3`

Top 3 shortlisted stocks:

1. `Piramal Finance Limited` - score `306.23`
2. `Tata Power` - score `178.05`
3. `Reliance Industries` - score `116.87`

Stage funnel counts:

- after fetch: `165`
- after RVOL: `18`
- after VWAP: `9`
- after opening range: `6`
- after volume acceleration: `3`

Filter reason counts:

- RVOL failure: `147`
- below VWAP: `9`
- opening range breakout: `3`
- volume acceleration: `2`
- volume acceleration unavailable: `1`

### 5.1 What this means

Stage 2 is doing what a good narrowing stage should do: it is extremely selective.

The most important observation is that RVOL is the dominant bottleneck. That may be fine, but it means your shortlist is heavily governed by one metric family. If the time-of-day RVOL method is noisy, overly strict, or miscalibrated for the late-session environment, it can distort the whole pipeline.

### 5.2 Strengths of Stage 2

- good compositional logic: RVOL, VWAP, ORB, and volume acceleration are coherent for intraday momentum discovery
- strong funnel reporting
- near-miss tracking is excellent and genuinely useful
- ranking after pass/fail avoids mixing unqualified names with qualified names

### 5.3 Weaknesses of Stage 2

#### A. Stage 2 is more of a hard filter than a flexible ranking engine

A stock can miss by tiny margins and still be discarded. Example from near misses:

- Adani Enterprises had `time_of_day_rvol = 1.3` and still appears as a near miss
- Chennai Petroleum barely missed volume acceleration

This is not wrong, but it means the shortlist is threshold-sensitive.

For intraday trading, threshold sensitivity can create instability:

- one minute later the top-3 may change sharply
- small data noise can flip pass/fail states

#### B. No explicit sector or cross-sectional normalization in the stock shortlist itself

The regime lane considers sectors, but the stage-2 stock scoring itself is mostly symbol-local. That means late-stage ranking may favor whichever names show the strongest micro burst, even if sector confirmation is weak.

#### C. Design mismatch with architecture note

The original architecture note describes a “single champion stock” cache model. The implemented system currently produces a top 3 shortlist.

This is not a bug. In fact, top 3 is probably better for the next phase. But the intended design and current implementation have diverged.

### 5.4 Stage 2 evaluation

- signal design quality: `8/10`
- explainability: `8.5/10`
- resilience to noisy thresholds: `6/10`
- suitability for feeding a human or agent analyst: `8.5/10`

Conclusion:

Stage 2 is one of the strongest parts of the current system.

## 6. Step-by-step analysis of the monitor system

Implementation file:

- [stage2_liquidity_gate.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/stage2_liquidity_gate.py)

Monitor gates:

1. Stage 2 shortlist exists
2. tick stats file exists
3. tick stats freshness is acceptable
4. tick collector warmup is sufficient
5. tick coverage ratio is sufficient
6. tick universe signature matches current shortlist
7. live quotes are available
8. per-stock checks pass:
   - spread <= `0.30%`
   - ticks in last 10 minutes >= `50`
   - RVOL >= `1.0`

Observed runtime behavior:

- monitor started at `15:00:27`
- it had been waiting for Stage 2 output since `14:50:57`
- stage2 output arrived around `15:00:27`
- tick collector started immediately
- monitor snapshot status became `waiting_for_tick_stats`
- tick stats after 61 seconds:
  - Reliance: `42`
  - Tata Power: `24`
  - Piramal Finance: `11`

### 6.1 What this means

The monitor is architecturally reasonable. It is trying to answer:

"Of the shortlisted momentum names, which ones are liquid enough right now to deserve final attention?"

That is a very good question to ask before final decisioning.

But the observed data also shows why it did not advance yet:

- warmup threshold is `120 seconds`
- minimum tick rate is `50 ticks / 10 min`
- after about one minute, no symbol had enough observed tick activity

### 6.2 Strengths of the monitor

- explicit gating before trusting live liquidity metrics
- freshness and universe-sync checks are well thought out
- live spread plus tick-rate filtering is highly relevant for intraday execution quality
- the tick collector preserves rolling activity windows

### 6.3 Weaknesses of the monitor

#### A. Monitor startup is too dependent on Stage 2 availability

It waited roughly `9.5 minutes` for Stage 2 output.

This means the services are technically separate, but operationally serial at startup.

That is acceptable in a prototype, but it reduces real-time responsiveness.

#### B. Tick collector data is activity count only

Current saved tick stats contain:

- ticks_last_10min
- ticks_last_30min
- ticks_last_60min
- ticks_today

But they do not persist:

- trade price sequence
- trade size sequence
- last trade timestamp
- aggressor side inference
- bid/ask imbalance over time

So the monitor can detect “activity,” but not true order-flow quality.

#### C. Field naming is semantically confusing

The monitor uses `stage2_reason` to store monitor rejection reasons. That is minor technically, but confusing architecturally because monitor is a distinct stage.

#### D. Duplicate data fetching still exists

Stage 2 fetches intraday history per stock. The monitor fetches intraday history per stock again. This is clean from an isolation standpoint but somewhat wasteful.

### 6.4 Monitor evaluation

- microstructure awareness: `6.5/10`
- gating discipline: `8/10`
- live data richness: `5/10`
- operational readiness: `6/10`

Conclusion:

The monitor is a valuable layer, but it is still a liquidity proxy, not a real microstructure analyzer.

## 7. Step-by-step analysis of the regime analysis system

Implementation file:

- [regime_analyzer.py](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/regime/regime_analyzer.py)

This lane is one of the more interesting parts of the architecture because it is not using stock-selection outputs as input. Instead, it builds market context from:

- primary indices
- sector indices
- index futures
- option chains
- BSE-originated market news and disclosures
- optional external input files in `python-backend/regime_inputs`

Observed regime output:

- market session: `live_market`
- market regime: `choppy`
- confidence: `64.88`
- trade permission: `reduced`
- preferred style: `observer_only`
- position size multiplier: `0.35`
- max concurrent positions: `1`

Important diagnostics:

- primary indices above open ratio: `0.0`
- primary indices above VWAP ratio: `0.0`
- sector breadth ratio: `0.4`
- breakout ratio: `0.3077`
- futures alignment ratio: `0.6667`
- vix change: `-2.4483`
- news severity: `0.15`

### 7.1 Strengths of the regime lane

#### A. Correct architectural independence

This lane is not contaminated by the stock shortlist. That is the right design. A market-regime model should stay market-wide.

#### B. Good blend of deterministic and probabilistic inputs

It mixes:

- deterministic market calculations
- structured option-chain diagnostics
- news summarization
- control policy mapping

That is much better than using an LLM alone.

#### C. Useful operational control output

The regime lane does not just label the market; it translates regime into:

- trade permission
- style preference
- size multiplier
- bias
- max concurrent positions

That is exactly the kind of output downstream risk and execution layers need.

### 7.2 Weaknesses of the regime lane

#### A. External input coverage is thin today

Missing today:

- market_breadth
- market_movers
- market_attention
- market_derivatives

Only `market_news` was provided.

So the regime lane is currently good, but not fully fed.

#### B. LLM integration is useful but should remain non-authoritative

The Agno/OpenRouter analysis produced a sensible neutral summary. That is a positive sign.

But regime-level policy should remain primarily deterministic. The LLM should add explanation and soft overlay, not become the source of truth for trade permission.

#### C. Review interval may be coarse for intraday volatility shifts

Current loop interval is `900 seconds` (15 minutes). For a broad regime lane this is acceptable, but for active intraday execution, a regime shift can matter faster than that.

### 7.3 Regime evaluation

- market context modeling: `8.5/10`
- separation of concerns: `9/10`
- operational usefulness: `8.5/10`
- completeness of current inputs: `6.5/10`

Conclusion:

The regime system is currently the most architecturally mature lane in the stack.

## 8. Analysis of local persisted data

The system’s local persistence is simple but useful.

Files observed:

- `stage1-2026-04-28.json`
- `stage1_universe_latest.json`
- `stage2-2026-04-28.json`
- `stage2_momentum_latest.json`
- `monitor-2026-04-28.json`
- `monitor_liquidity_latest.json`
- `regime-2026-04-28.json`
- `regime_latest.json`
- `stage2-tick-stats-2026-04-28.json`
- `stage2-tick-history-2026-04-28.json`

### 8.1 What is good about the local storage pattern

- easy to inspect manually
- excellent for debugging and audit during development
- snapshots are human-readable
- latest + dated snapshot pattern is helpful

### 8.2 What is weak about the local storage pattern

- no transactional coordination
- risk of partial-write or stale-read behavior
- not ideal for concurrent multi-service orchestration at scale
- no durable event lineage
- difficult to support replay, backtest audit, and decision explainability at production quality

### 8.3 A subtle but important issue

Different lanes save different payload shapes.

For example:

- stage snapshots use `summary` plus `stocks`
- tick stats are not wrapped in the same stage payload style

That is not fatal, but it increases cognitive load and integration friction for later agents and APIs.

Recommendation:

Move toward a common envelope schema such as:

- `stage`
- `market_date`
- `generated_at_utc`
- `schema_version`
- `summary`
- `inputs`
- `artifacts`
- `records`
- `diagnostics`

## 9. Architecture evaluation from multiple angles

### 9.1 Modularity

Assessment: good

The system is split into meaningful layers:

- discovery
- validation
- regime context
- data services
- runtime loops

This is one of the strongest qualities of the current architecture.

Score: `8/10`

### 9.2 Observability

Assessment: decent for a prototype

The logs are verbose and helpful. Persisted JSON outputs are useful. Funnel counts and reason counts are especially strong.

What is missing:

- structured metrics
- alerts
- end-to-end correlation IDs
- latency accounting per stage and per symbol
- outcome tracking across the whole trade lifecycle

Score: `7/10`

### 9.3 Data quality and trust

Assessment: mixed

Strengths:

- high transparency
- explicit failure handling
- fallback-safe behavior in several places

Weaknesses:

- empty surveillance inputs today
- repeated dependency on external API completeness
- live tick stats still shallow

Score: `5.5/10`

### 9.4 Latency and timeliness

Assessment: fair, not great

Strengths:

- Stage 2 shortlist itself was produced quickly after Stage 1 completed
- regime loop is independent

Weaknesses:

- Stage 1 takes several minutes
- monitor waits on file availability
- monitor then waits again on collector warmup
- downstream action path is not event-driven

Score: `6/10`

### 9.5 Suitability for intraday momentum trading

Assessment: good on discovery, incomplete on execution

Why good:

- momentum criteria are sensible
- live liquidity gating is relevant
- regime overlay is appropriate

Why incomplete:

- no final trade decision engine yet
- no portfolio-aware risk logic yet
- no proper order-flow or execution-quality analyzer yet

Score: `7/10`

### 9.6 Production readiness

Assessment: not yet production-grade

Needs before that label is deserved:

- durable orchestration
- stronger market-data validation
- better recovery behavior
- full risk controls
- deterministic final decision policy
- post-trade monitoring and kill switches

Score: `4.5/10`

## 10. Important architecture mismatches and hidden risks

### 10.1 Intended “one champion stock” vs actual “top 3 shortlist”

This is actually a healthy divergence. The next phase should keep top 3, not revert to top 1.

Reason:

- top 1 too early creates unnecessary single-point model risk
- top 3 lets later specialist agents compare relative conviction
- the risk agent benefits from choice under context

### 10.2 Current monitor is not true order-flow analysis

The future design mentions order-flow candlestick charts and order-flow context. Current monitor only measures:

- spread
- tick rate
- RVOL

That is useful, but it is not order-flow analysis.

### 10.3 File-based coordination will become painful in the next phase

Once you introduce:

- 3 stock-analyzer agents
- 1 risk agent
- 1 execution agent
- chart image generation
- portfolio context
- richer inputs per symbol

the current file-polling model will become difficult to reason about and hard to scale safely.

## 11. Deep analysis of the next-phase implementation plan

Your next-phase idea is strong in principle:

1. keep the current system as a discovery layer
2. create 3 separate stock analysis instances for the top 3 names
3. pass regime context and chart artifacts into each analyzer
4. pass resulting reports to a risk-monitoring agent
5. pick one stock
6. pass the chosen-stock dossier to an execution agent

This is a good architecture direction, but only if it is implemented as a disciplined decision pipeline rather than as a loose conversation among agents.

## 12. Why the next-phase idea is good

### 12.1 It preserves specialization

You are separating:

- discovery
- single-stock deep analysis
- portfolio-aware risk selection
- execution approval

That is much better than asking one general agent to do all of it.

### 12.2 It upgrades from absolute ranking to comparative decisioning

Current system says:

- “these are the best-looking names according to discovery filters”

Next system would say:

- “among the best-looking names, which one is best after deeper technical, contextual, and risk-aware review?”

That is a real improvement.

### 12.3 It makes the regime lane more useful

Right now regime produces controls, but there is no true downstream consumer. The risk and execution layers would finally make regime actionable.

## 13. The biggest risks in the next-phase idea

### 13.1 Agent sprawl risk

If the analyzers are too free-form, you may get:

- long beautiful reports
- inconsistent criteria across agents
- unstable outputs from one run to the next
- hard-to-debug trade decisions

For trading, this is dangerous.

### 13.2 Duplicate reasoning over weak inputs

If the data package is incomplete, three analyzers will not create three times the truth. They will create three times the narrative around the same missing data.

### 13.3 Execution agent becoming a second uncontrolled opinion layer

If the execution agent is allowed to override both stock analyzers and risk without a strict policy, you create a blurry chain of responsibility.

For trading systems, blurry responsibility is bad architecture.

## 14. Recommended architecture for the next phase

Do not implement the next phase as “many agents talking.”

Implement it as:

### 14.1 Deterministic pipeline plus bounded agent roles

Use agents only for bounded interpretation tasks.

Recommended stack:

1. deterministic data pack builder
2. deterministic chart/artifact builder
3. three bounded stock-analysis agents
4. deterministic report normalizer
5. portfolio-aware risk decision engine
6. execution decision engine with veto logic

### 14.2 Proposed contracts

#### Contract A: Candidate packet

For each shortlisted stock, build one machine-readable packet containing:

- symbol metadata
- Stage 1 features
- Stage 2 features
- latest monitor features
- regime summary
- sector context
- intraday candles: 1m, 5m, 15m
- optional order-flow features
- optional indicator bundle
- chart image paths
- timestamp and freshness metadata

#### Contract B: Analyzer output

Each stock analyzer should return a strict JSON schema, not free text only.

Suggested fields:

- `symbol`
- `direction_bias` (`long`, `short`, `avoid`)
- `setup_type`
- `confidence`
- `entry_zone`
- `stop_zone`
- `target_zone`
- `invalidation_conditions`
- `supporting_evidence`
- `contradicting_evidence`
- `regime_alignment`
- `execution_quality`
- `summary_for_risk_agent`

#### Contract C: Risk agent output

Inputs:

- the 3 normalized analyzer outputs
- user portfolio
- live positions
- holdings
- balance
- regime controls

Outputs:

- `selected_symbol`
- `rejected_symbols`
- `portfolio_risk_assessment`
- `position_size_cap`
- `max_loss_allowed`
- `regime_compliance`
- `rejection_reason_if_none`

#### Contract D: Execution agent output

This should be the final gate, not a second analyst.

Inputs:

- chosen stock packet
- analyzer normalized report
- risk decision
- live account context
- latest quote / spread / optional depth

Outputs:

- `execute` true/false
- `side`
- `entry_type`
- `entry_price_logic`
- `stop_loss`
- `target`
- `quantity`
- `execution_constraints`
- `final_veto_reason`

## 15. Should there be 3 separate stock analyzer instances?

Yes, but with a very important caveat.

Use 3 separate instances because the stocks are different, not because you want 3 different personalities or strategies.

Each instance should use the same prompt contract and scoring rubric.

Good:

- one analyzer instance per stock
- same schema
- same evidence checklist
- same output contract

Bad:

- three differently instructed agents
- one bullish, one discretionary, one “creative”
- narrative-only outputs

## 16. What additional data should feed the stock analyzers

Your proposed additions are directionally correct.

Recommended minimum input set:

1. 1-minute candles
2. 5-minute candles
3. 15-minute candles
4. intraday VWAP
5. opening range high/low
6. RVOL
7. volume acceleration
8. spread
9. tick rate
10. sector index state
11. regime summary

Recommended next-level inputs:

12. rolling support/resistance zones
13. day high / low proximity
14. distance from prior day high / low / close
15. ATR-normalized stop estimates
16. candle structure features
17. simple pattern detections

Only after that should you consider advanced order-flow features:

18. best bid / ask imbalance
19. short-term depth imbalance
20. trade aggressor approximation
21. absorption / sweep heuristics
22. volume delta proxies

Do not jump directly to chart images without first ensuring the underlying structured features are available.

## 17. About candlestick images and order-flow charts

Images are useful, but they should be secondary evidence.

Best use:

- human review
- multimodal model support
- visual confirmation of pattern shape

Not best use:

- primary truth source for deterministic decisions

Recommendation:

- generate charts as artifacts
- also compute the numeric features that those charts imply
- keep the agent from depending only on vision

## 18. How the risk agent should really work

The risk agent should be closer to a policy engine than an opinion agent.

Its job is not:

- “which story sounds nicest?”

Its job is:

- “which candidate best fits account constraints, regime controls, and execution reality?”

Risk checks should include:

- per-trade loss cap
- daily loss cap
- existing exposure by sector and direction
- correlation to current holdings
- leverage constraints
- regime permission
- spread and liquidity quality
- stop distance sanity
- reward/risk minimum

If these checks are deterministic, the risk agent becomes much more trustworthy.

## 19. How the execution agent should really work

The execution agent should be the final operational checker, not a third subjective analyst.

It should answer:

1. Is the selected trade still valid now?
2. Is spread acceptable now?
3. Is slippage risk acceptable now?
4. Is the stop/size still valid under current quote?
5. Has the regime materially changed?
6. Has the setup already moved too far from the intended entry?

If yes, it executes.
If no, it vetoes.

That is enough.

## 20. Recommended implementation sequence for the next phase

### Phase A: Strengthen the current discovery stack first

Before building agents, fix:

1. surveillance input reliability
2. monitor maturity and tick-data richness
3. common schema for saved outputs
4. event/freshness metadata

### Phase B: Build candidate packet generation

Create one deterministic “candidate dossier builder” that takes the current top 3 and produces the full structured packet per stock.

This is the most important enabling step.

### Phase C: Build chart artifact generation

Per stock:

- 5m candlestick chart
- 15m candlestick chart
- optional order-flow / liquidity panel

Save these to disk and reference them from the packet.

### Phase D: Build the stock analyzer contract

Implement analyzer outputs as strict JSON plus optional long-form commentary.

### Phase E: Build portfolio-aware risk selection

This is where the first true trade selection should happen.

### Phase F: Build execution veto and order instruction builder

Only after the above should orders be prepared.

## 21. Recommended architectural upgrades before or during next phase

### 21.1 Introduce a canonical data model

This will reduce chaos dramatically.

### 21.2 Add a lightweight event bus or job queue

Current file polling is okay for prototype work, but the next phase will benefit from:

- Redis streams
- a message queue
- or even a small database-backed job/event table

### 21.3 Store decision lineage

Every final trade decision should know:

- which Stage 2 snapshot it came from
- which regime snapshot it used
- which monitor snapshot it used
- which analyzer outputs it used
- which risk controls were applied

### 21.4 Separate “analysis” from “approval”

This is crucial.

- stock analyzers analyze
- risk approves or rejects
- execution confirms live tradability

Do not let all three layers behave like analysts.

## 22. Final evaluation

### Current system overall

The current architecture is better than a simple scanner and already shows thoughtful engineering. The strongest parts are the staged design, persisted outputs, and regime/control separation. The weakest parts are operational coupling through files, surveillance input trust, shallow live microstructure data, and the absence of a formal final decision path.

Overall score for current system as it exists today:

- discovery engine quality: `7.8/10`
- regime/context engine quality: `8.4/10`
- live tradability assessment quality: `6.2/10`
- end-to-end autonomous trading readiness: `5.2/10`

### Next phase overall

Your next-phase direction is good and worth building, but it should be implemented as a controlled multi-stage decision system with strict schemas, not as unconstrained multi-agent discussion.

Overall score for the next-phase concept:

- concept quality: `8.6/10`
- risk if implemented loosely: `high`
- expected value if implemented with strict contracts: `very good`

## 23. Practical conclusion

If we say it plainly:

- the current system is a strong shortlist generator
- the regime engine is already useful
- the monitor is promising but still shallow
- the architecture is good enough to extend
- the next phase should absolutely keep top 3 rather than collapsing to top 1 too early
- the next phase should be contract-driven, portfolio-aware, and veto-based

The best next move is not to start with “three smart agents.”

The best next move is:

1. build the candidate dossier format
2. enrich the live data package
3. normalize the analyzer outputs
4. make risk and execution layers deterministic wherever possible

That path will give you a system that is far more stable, explainable, and actually usable for intraday trading.
