# Trader research review

September 5, 2026 · Stage 1, Intra-Finder, stock agents and execution

Prepared for the owner and developer of Trader. Scope: recorded Indian equity sessions from August 31 through September 4, current implementation, and relevant primary documentation. This is an analysis report; no application code or runtime configuration was changed.

## Assessment

Keep the broad Stage 1 universe and the separation between market observation and account execution. The most urgent work is the contract between Intra-Finder, the stock agent and the execution service. That contract is incomplete, and it creates avoidable analysis, contradictory decisions and stale order attempts.

The data supports concrete engineering changes now. It does not establish the profitability of the complete trading system. There are four dates with recordings spanning the regular session, with interruptions, and one additional partial date. Only August 31 and September 1 have completed agent decisions in the inspected archives. September 2–4 were scanner shadow sessions.

Three findings deserve priority:

1. All 199 inspected agent decision snapshots omit the scanner's setup type, required direction, expiry, trigger level and invalidation level. The execution toolkit nevertheless enforces the scanner direction. On September 1, 22 agents discovered that restriction through a failed sizing call.
2. Account capacity is checked too late. August 31 produced 61 order-tool rejections for full trade slots after the expensive analysis. In 55 of those cases, the initial snapshot already showed three open intraday positions.
3. Median event-to-first-order-attempt time was 73.8 seconds on August 31 and 91.3 seconds on September 1. The underlying scanner events expire after 30 or 45 seconds. The application needs explicit analysis and order validity rules, supported by fresh evidence at submission.

These findings come from joining the [decision archive](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson), [dispatch state](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-dispatch-state.json), daily scanner events and recorded tool timelines. Their implications are developed below.

## What data actually exists

| Date | Persisted scanner events | Distinct event stocks | Recorded one-second rows | Recording span, IST | Agent evidence |
|---|---:|---:|---:|---|---|
| Aug 31 | 505 | 98 | 5,670,538 | 09:10:05–15:30:01 | 125 completed stock reports |
| Sep 1 | 225 | 81 | 9,202,733 | 09:10:20–15:30:09 | 74 completed stock reports |
| Sep 2 | 650 | 111 | 10,965,396 | 09:10:24–15:30:09 | Shadow; no dispatch |
| Sep 3 | 842 | 126 | 11,805,519 | 09:10:23–15:30:18 | Shadow; no dispatch |
| Sep 4 | 37 | 23 | 680,956 | 13:09:12–13:29:07 | Shadow; partial session |

Total: 2,259 persisted events. A recording span does not prove uninterrupted coverage. Rows are observations, not independent trades, and one-second files only contain stocks that received updates.

The laptop supplied the first two dates. Ubuntu supplied September 2–4 under `/app/python-backend/results` inside the containers. The Ubuntu agent directory contained an old latest result and dispatch state, but no new decision archive. Its latest result matched the September 1 laptop artifact by size, and its state referenced older completed events. The new scanner records explicitly have `shadow_mode=true`.

September 3's status file says 1,492 events formed. The durable event file contains 842 unique IDs. The difference is exactly September 2's 650 events. Code initializes these counters in the constructor but does not reset them when releasing session state. The status value is therefore a process-lifetime total presented under a daily market date. The 36.87 million packet total must also not be called September 3's daily packet count without taking a start-of-day difference. September 4's final status was overwritten with zero counts after session state release.

Use the append-only event file for event totals. Fix daily counters and preserve immutable end-of-session summaries. Current evidence files are [Aug 31 events](C:/Users/prajw/Downloads/Trader/python-backend/results/stage2/2026-08-31/setup-events.jsonl) and [Sep 1 events](C:/Users/prajw/Downloads/Trader/python-backend/results/stage2/2026-09-01/setup-events.jsonl); Ubuntu paths are identified above because they are not laptop files.

## The candidate-to-order funnel

| Stage or outcome | Aug 31 | Sep 1 |
|---|---:|---:|
| Scanner events | 505 | 225 |
| Dispatch state marked blocked | 48 | 139 |
| Dispatch state still marked started | 3 | 3 |
| No dispatch-state entry | 1 | 0 |
| Archived orchestration failures | 12 | 9 |
| Completed orchestration records | 441 | 74 |
| Completed records rejected by user eligibility | 316 | 0 |
| Completed stock-agent reports | 125 | 74 |
| Agents that called the order tool | 89 | 55 |
| Order-tool calls, including retries | 92 | 58 |
| Final status `traded` | 12 | 16 |
| Final status `part_traded` | 1 | 0 |
| Final status `pending` | 3 | 8 |
| Final status `failed` within completed reports | 12 | 25 |
| Final status `blocked` within completed reports | 61 | 6 |
| Final status `skipped`, no final order result | 36 | 19 |

The top-level stages reconcile to the scanner totals. The lower outcome rows reconcile to the completed stock reports. Do not sum rows across levels of the funnel.

On August 31, 312 eligibility rejections reported `available_balance_unavailable`, three reported that a margin allocation could not support one share, and one reported excessive user slippage. The balance status combines unavailable and zero balance; the stored reason does not establish an API outage versus exhausted funds.

Of the 21 archived orchestration failures across both dates, 11 contained `stock_agent_empty_response` and ten contained intraday-history failures caused by local rate-limit cooldown. These failures can include partial work, so 199 is the number of completed stored reports, not a verified count of every model request ever started.

Across the 199 completed reports, 144 agents attempted an order, 72.4%. Only 28 have a final saved `traded` status, 14.1%, plus one partial status. Calling the agents excessively cautious based on final `avoid` labels would be incorrect. The application derives `action` from the execution result. A proposed trade rejected by a guard becomes `avoid`, just as a deliberate abstention does. See [execution result mapping](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stock/toolkits/execution_toolkit.py:315).

The saved status is not a complete fill ledger. One Remsons record has `part_traded` with zero recorded filled quantity. One Indo Rama record says `traded` while showing four filled against ten requested. There are 11 pending records whose eventual outcomes are not reconciled in this review. Actual entry fills, exit fills, fees and realized P&L cannot be certified from these snapshots. Dhan's order-update protocol provides quantities, traded prices and order timestamps needed for that reconciliation. [Dhan Live Order Update](https://dhanhq.co/docs/v2/order-update/)

## What the agents are saying

Every completed report was included in structured and text screening. Decision-bearing excerpts were reviewed across all 199 reports, with complete reports, snapshots and tool results inspected for the case studies below. This is not a claim that every chart or every reasoning-token stream received a complete visual or semantic audit.

The agents usually reason from price versus VWAP, trend and EMA state, prior-session levels, short-term support/resistance, volume and a proposed stop/target. A text screen found VWAP in 194 reports, volume or RVOL in 193, risk/reward language in 134, retest or pullback language in 104, and book/depth/imbalance language in 60. These are mention counts, not correctness scores.

There are useful abstentions. Indoco Remedies declined a mid-range opening entry and described what would need to break before a trade made sense. Several reports reject chasing large extensions or duplicating an existing position. Those are valuable behaviors worth preserving.

There are also repeated reasoning faults.

### The execution constraint becomes a supposed market signal

On September 1, 22 of 74 completed agents encountered `side_conflicts_with_detector_direction`. Five subsequently have `traded` status, two pending, five blocked, seven failed and three skipped.

Cosmo First initially proposed a short. After the sizing tool rejected that side, the agent said the detector aligned with a long and bought one share. Sonam initially proposed a short, then used the permitted BUY direction to justify a counter-trend bounce. The tool had disclosed a workflow constraint, not new independent evidence that the market favored the opposite trade.

Cyient provides a better response to the same conflict. It explicitly declined to force a counter-trend long without a bullish reversal trigger. That is the behavior to standardize. [Cosmo report](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson:842), [Sonam report](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson:852), [Cyient report](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson:866)

The cause is visible in code. [Market evidence construction](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stock/toolkits/market_data_toolkit.py:82) selects quote, volume and depth fields but omits the setup contract. [Agent construction](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/runtime/run_stock_agent.py:837) separately gives the execution toolkit an allowed side. The model sees only the compact decision context.

Pass the setup hypothesis, direction, trigger, invalidation, expiry and evidence timestamps to the agent before analysis. Ask it to accept or reject that hypothesis. If the architecture permits the agent to originate a different trade, record a new proposal with its own evidence and validity, rather than treating a side change as confirmation of the old event.

### High volume becomes unsupported ownership or intent

Thirty-six reports mention institutions or smart money. Not every mention is an unsupported claim, but the Transformers & Rectifiers report explicitly infers “strong institutional accumulation” from opening volume and RVOL. The supplied data does not identify who traded. The same report describes a clear momentum-continuation day only seconds after the opening auction.

Dhan's documented Full packet contains trade and depth fields, not participant identity. Require statements about observable behavior, such as rising price on elevated volume, and label explanations about participant intent as unverified. [Transformers report](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson:361), [Dhan packet fields](https://dhanhq.co/docs/v2/live-market-feed/)

### Numeric and time concepts sometimes drift

Indo Rama describes its ₹65.80 stop as above VWAP ₹65.86 in one table, then correctly calls it below VWAP later in the same report. Ashoka Buildcon calls its approximately 13% advance from previous close an opening gap, even though other session evidence gives an open around ₹117.70 against ₹112.92, approximately 4.2%.

These are small examples of a broad requirement: calculate gap, return, stop distance, target room and reward/risk in deterministic code, and give the agent those values with their time basis. Do not depend on prose arithmetic. [Indo Rama report](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson:384), [Ashoka report](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson:425)

For the 28 records marked traded, the median proposed reward/risk was 1.61 on August 31 and 1.69 on September 1. Nine were below 1.5. This is not automatically unacceptable; the needed win probability depends on costs and realized payoff distributions. It does mean that strong-conviction wording is not a substitute for calibrated probabilities and realistic costs.

### The agent is asked to recover without the required tools

The current agent has only sizing and protected-order tools, and a three-call limit. The normal path consumes two calls. After a placement rejection, resizing and placing again require two further calls. Reports repeatedly end with attempted recovery blocked by the call limit. A narrow text screen found this pattern in three August 31 reports and 11 September 1 reports.

The problem is not solved by allowing unlimited calls. Use a single validated proposal followed by deterministic sizing and submission. If a fresh quote invalidates the proposal, return a structured rejection. Permit one explicitly bounded re-analysis only when the setup still qualifies and fresh evidence is available. The current [agent instructions and tool limit](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stock/stock_agent.py:49) should match that workflow.

Eleven reports contain a narrow pattern promising future monitoring. A per-event agent returning a final answer does not itself establish a persistent monitor. Display the actual order-management owner and state instead of relying on those promises.

## Latency and wasted work

| Measurement | Aug 31 median | Sep 1 median |
|---|---:|---:|
| Event to charts built | 8.7 s | 9.6 s |
| Stored model-run duration | 68.1 s | 90.8 s |
| Event to first order-tool call | 73.8 s | 91.3 s |
| Event to completed report | 81.6 s | 108.7 s |
| Reported input tokens per measured run | 33,064 | 43,792 |
| Reported output tokens per measured run | 6,201 | 7,962 |
| Reported reasoning tokens per measured run | 5,256 | 7,129 |

Model metrics exist for 113 of 125 reports on August 31 and 73 of 74 on September 1. Their durations include the model workflow and cannot be read as isolated network latency. Their token counts can aggregate multiple model calls. Median stage durations must not be added as if they came from the same run.

Of 144 first order attempts, 141 occurred after the original event expiry. This is a mismatch of validity semantics, not proof that every order used a stale current quote. The execution service does fetch and validate current market information. Admission expiry and final trade-plan validity need distinct names and enforcement points.

Measured placement failures show why that matters. Across 150 order-tool calls, 25 reported excessive price drift, six reported final price invalidating the setup, seven reported stale quotes, three reported stale candle data, 67 reported full trade slots, and two reported an existing position or active order on the assigned stock. Forty calls returned success, which includes pending orders and does not mean forty final fills.

The cheapest optimization is to avoid starting analysis when the account already cannot accept an order. Northern Arc's initial snapshot showed three positions, but the agent still sized and attempted a new trade before learning the three-slot limit. This pattern repeats. Use account eligibility and capacity reservations before chart generation, then revalidate at submission to handle races. Continue scanner recording while the account is unavailable. [Northern Arc case](C:/Users/prajw/Downloads/Trader/python-backend/results/agents/event-decision-archive.ndjson:386)

The model workflow is the largest measured component of completed decisions. Benchmark a compact structured proposal, reduced reasoning budget and fewer decision-relevant charts against the existing eight-chart workflow on identical snapshots. Keep charts that measurably change correct decisions. Generate presentation reports after the order decision rather than extending the decision path.

Prompt-prefix caching is already reflected in the stored token metrics; it cannot alone explain away the long durations. Keep stable instructions first and dynamic evidence later, and measure cache hits. Do not cache completed live trading responses as a shortcut. Agno documents that response-cache hits return before tools execute. [OpenRouter prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching), [Agno response caching](https://docs.agno.com/models/cache-response)

A structured proposal can contain disposition, allowed direction, entry condition, stop, target, evidence timestamps, thesis invalidation and concise supporting observations. Validate arithmetic and identity after generation. Endpoint support for JSON Schema must be enforced; syntactically valid output does not establish a correct trade. [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)

## Runtime reliability and research correctness

The independent source audit verified matching SHA256 hashes for the laptop and current Ubuntu copies of Intra-Finder, live state and activity ranker.

**Packet processing blocks ingestion.** The service receives a packet, processes it synchronously and runs due ranking before reading the next one. September 3's 375 periodic rank samples have a median of 1.15 seconds, p95 3.55 seconds, p99 7.91 seconds and maximum 11.49 seconds. These are sampled status observations, not all-rank latency percentiles. A several-second rank can delay ingestion and WebSocket servicing. Separate network ingress from ranking and recording, timestamp at ingress, and measure pending-data age. Choose threads versus processes after profiling; Python threads alone do not isolate CPU work. [Receive path](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/intra_finder.py:1077), [rank call](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/intra_finder.py:444)

**Opening-range completeness is inconsistent.** Live state can mark a range complete after any pre-09:30 observation followed by a post-09:30 packet. Historical repair requires substantially more minute coverage. A partial live range can therefore be marked complete and avoid repair. Track observation coverage and gaps, distinguish observed from verified ranges, and repair incomplete intervals. [Opening-range state](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/live_state.py:246)

**Confirmation can span an unobserved gap.** Setup evaluation only runs for eligible top-ranked stocks. Leaving eligibility does not reset an armed tracker, while confirmation uses elapsed wall time. A stock can return and satisfy the hold duration without continuous qualifying observations. Expire or suspend armed states on eligibility loss, disconnection and excessive observation gaps. [Setup confirmation](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/setups/base.py:69)

**Persistence failures can disappear.** Completed I/O futures are discarded without checking exceptions, and buffers have already been detached from live state. This is a verified failure path, not evidence that records were actually lost. Bound pending writes, acknowledge successful persistence, retain failed batches and expose recorder health. Event-state rewrites and full status/checkpoint construction should move off the ingestion path. [I/O submission](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/intra_finder.py:858)

**Success metrics are misleading at two levels.** Scanner dispatch success means HTTP success, even when the gateway returns a normal response saying admission was blocked. Separately, the archived tool summary labels all 340 completed tool calls successful, with zero failures. The actual result payloads include 65 failures and 67 blocks. The summary checks transport/event type rather than domain status. Preserve both, with distinct names. [Dispatch response handling](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/intra_finder.py:684), [tool summary](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stock/stock_agent.py:276)

**Capacity reservations have a race.** Thread sets are pruned by `is_alive()` before another submitter's reserved thread necessarily starts. Use an explicit reservation or semaphore rather than thread liveness as the capacity contract. No capacity overrun is claimed from these data; this is a code-level risk.

**Historical quality remains variable.** Stage 1 profile coverage improved to 3,368/3,526 on September 2, then fell to 2,094/3,526 on September 3 before recovering to 3,321/3,478 on September 4. Baselines remained broadly available. The earlier claim that coverage had simply converged with cache warming was too confident. Preserve completed historical profiles through transient fetch failures and prevent incomplete comparisons from forcing venue changes.

There is no need to shrink the broad universe merely because history requests fail. Approximately 3,500 instruments fit Dhan's documented 5,000-instrument connection limit. The account-wide history budget is five requests per second. Share that budget across profiling, repair and agents, and reuse completed candles. [Dhan feed limits](https://dhanhq.co/docs/v2/live-market-feed/), [Dhan rate limits](https://dhanhq.co/docs/v2/)

Dhan's packet timestamp is last trade time, not a separately documented depth-generation timestamp. Local processing time minus last trade time does not measure pure transport latency. Record ingress and processing times separately, and label trading inactivity separately from queue delay. [Dhan packet fields](https://dhanhq.co/docs/v2/live-market-feed/)

## What can be concluded about accuracy

The previous report overstated what a scanner-direction return test proves. Intra-Finder supplies a hypothesis to an agent that may wait, reject it, choose another entry or, historically, trade the other direction. Scanner returns cannot establish the incremental value of that agent.

I repeated the laptop diagnostic with stricter timestamp handling. For each event, entry uses its recorded ask for a long or bid for a short. The five-minute exit must have a valid non-crossed bid/ask observation within five seconds after the target horizon. Missing quotes are excluded, not silently replaced with a much later observation.

| Scanner-direction diagnostic | Aug 31 | Sep 1 |
|---|---:|---:|
| Events with usable five-minute exit | 367 / 505 | 181 / 225 |
| Mean hypothetical return | -0.0785% | -0.1134% |
| Median hypothetical return | -0.1176% | -0.1284% |

This remains unfavorable, but the changed denominators matter. Missing observations are probably not random, and one-second data can miss intrasecond price paths and depth changes. These are hypothetical quote-based markouts before fees and impact, not executable guarantees, actual strategy P&L or target/stop backtests.

I also tested the agents' first attempted direction at the quote observable around their first order-tool call, with the same five-second quote tolerance and a five-minute horizon:

| Hypothetical marketable entry at first attempt | Aug 31 | Sep 1 |
|---|---:|---:|
| Usable attempted-trade observations | 53 / 89 | 38 / 55 |
| Mean return | +0.1601% | -0.0992% |
| Median return | +0.1342% | -0.0638% |

This deliberately does not simulate the agents' actual limit fills, stops or targets. It demonstrates inconsistency and why attribution matters. It is not an apples-to-apples estimate of AI uplift: the cohorts, directions and entry times differ. Matched policy replay and broker reconciliation are still needed.

The original 0.20% target/stop experiment should not be used to declare every setup family untradeable. The agents often proposed larger stops and different horizons. Nor should retest, exhaustion or acceptance logic be presented as a proven cure. Those are testable hypotheses.

Current stale-NIFTY context handling has already been fixed: the loader checks market date and timestamp. It should not remain on the outstanding defect list. [Current context validation](C:/Users/prajw/Downloads/Trader/python-backend/pipeline/stages/intra_finder.py:826)

## Recommended architecture and order of work

Keep a compact sequence with explicit ownership:

1. A feed owner receives and timestamps data continuously, maintains bounded market state and records gaps.
2. A ranker selects active stocks and emits setup hypotheses using verified, versioned evidence.
3. An account admission service checks funds, existing exposure and capacity, then reserves analysis capacity.
4. One agent accepts or rejects the supplied hypothesis and produces a compact trade proposal.
5. A deterministic execution service refreshes relevant market/account facts, sizes, validates the proposal and submits an idempotent protected order.
6. Order updates reconcile acceptance, fills, protection, exits and costs into a durable ledger.

These can remain a small number of processes. No Kafka cluster, multi-agent debate or framework rewrite is justified by this evidence.

| Priority | Change | Evidence of completion |
|---|---|---|
| 1 | Supply setup contract and allowed direction before model invocation | No hidden-direction discovery; disagreements are explicit abstentions or separate proposals |
| 1 | Check and reserve account capacity before expensive analysis | No full-slot rejection that was already knowable at admission |
| 1 | Reconcile event, agent, order and fill statuses | Daily counts balance; partial and pending orders remain explicit |
| 1 | Define proposal validity and refresh before submission | Every order has current quote/account timestamps and a valid thesis |
| 2 | Isolate ingestion and verify opening-range coverage | Measured ingress-to-processing delay; no partial range labeled verified |
| 2 | Make persistence failures and queue age visible | Failed writes surface, retry or create an explicit recorded gap |
| 2 | Reduce model work and repeated tool turns | Lower p95 decision latency without worse held-out decision outcomes |
| 3 | Evaluate setup logic, cooldowns, spreads and chart subsets | Improvements persist on untouched data after costs and delay |

Choose a latency target from measured setup decay. Replay decisions delayed by 5, 15, 30, 60 and 90 seconds. A setup whose useful entry window disappears before the achievable decision time should not use that decision path. Faster model output alone is insufficient if the feed or evidence is stale.

Do not increase trade slots simply to make more orders go through. The five-slot change overlaps other deployment changes, so the increase from 12 to 16 traded statuses is not a controlled experiment. Early admission avoids wasted work without increasing exposure.

Do not blindly impose a 30–45 minute cooldown on every stock. Compare event episodes and label genuine new setups versus repeated alerts from the same move. Then test cooldown policies against both workload and missed opportunities.

## Data collection and evaluation plan

There is enough evidence to fix the integration and measurement defects. There is not enough independent, consistently recorded evidence to optimize a complete strategy with confidence.

Preserve complete candidate and rejection data, not only traded stocks. Each record should contain code/config/model versions, universe identity, setup episode, rank computation time, evidence timestamps, observed gaps, admission result, proposed direction and prices, order request/acknowledgment, actual fills, exits and costs. Save account availability as a separate condition so an unavailable account does not become a negative model label.

Evaluate the same point-in-time opportunities under three policies: deterministic candidate selection alone, the current agent, and the proposed compact agent workflow. Use chronological held-out days, preserve overlap between events in the analysis, and report uncertainty grouped by day and stock episode. Log every tried variant. Optimizing repeatedly on the same dates makes the best result look better than it is. Original research on the deflated Sharpe ratio explains the multiple-testing problem. [Bailey and López de Prado, 2014](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)

Do not use a fixed session count as a certification rule. Twenty clean sessions can be a collection milestone; forty or sixty are not guarantees either. Evidence requirements depend on effect size, variability, overlapping events, regime coverage, costs and the number of attempted variants. A useful stopping rule asks whether a prespecified uncertainty interval for net performance and drawdown is narrow enough for the decision, with acceptable outcomes on untouched periods.

Existing historical candles can broaden tests of price/volume logic. They cannot reconstruct missing order-book sequences or historical AI decisions. Keep those data classes separate. [Dhan historical data](https://dhanhq.co/docs/v2/historical-data/)

## Scope and remaining limits

The review reconciled all 730 scanner events from the two live-dispatch dates, all 536 matching orchestration archive records and all 199 completed stock reports. It screened the complete report texts and inspected full evidence for selected cases. It inspected Ubuntu daily event counts, recording spans, summaries and runtime logs for the newer dates. Other older-architecture dates in the archive were excluded from the quantitative agent cohort.

A delegated qualitative review stopped after a usage-limit error; its preliminary observations were treated as leads and the cited cases were checked directly. No claim of a full visual audit of every attached chart is made.

Ubuntu SSH authorization expired during a later follow-up and requested browser authentication. The earlier retrieved inventory and summaries remain evidence, but the stricter forward-return analysis was completed only for the laptop dates. September 3–4 forward-return results are not fabricated or inferred from scanner counts. Complete broker exit/fill records and separately stored cloud sessions were not retrieved, so realized P&L and the ultimate disposition of every pending order remain unresolved.

This report therefore supports an engineering priority list and specific observations about agent behavior. It does not certify trading accuracy, profitability or a replacement detector's edge. The highest-value next implementation is the complete setup/proposal contract plus early account admission and a reliable outcome ledger. Those changes make subsequent optimization measurable.
