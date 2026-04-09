
## Trading System Flow and Architecture Analysis

This document reflects the current working architecture and the intended next-step architecture after the recent refactors.

The most important change in thinking is this:

- not everything in the system is a numbered "stage"
- some parts are stock-sorting services
- some parts are market-context services
- some parts are live-confirmation services
- some parts will become AI decision services

That distinction matters because it prevents us from forcing unrelated responsibilities into one linear pipeline.

---

## 1. Current Practical Flow

### 1.1 `sorting` container

This is the main stock-selection lane.

Its job is:

1. Run Stage 1 before market action matters
2. Reuse that daily universe during market hours
3. Run Stage 2 every 10 minutes starting from market open
4. Keep producing a small, actionable shortlist

In practical terms:

- Around `8:45 AM` IST:
  - Stage 1 runs
  - it reduces the full BSE universe into a much safer daily candidate universe
- From `9:15 AM` onward:
  - Stage 2 runs every 10 minutes
  - it takes Stage 1 survivors and identifies which names are actually igniting right now

This is why the old `backend` name is not accurate anymore.
This service is not a generic backend.
It is specifically the **sorting engine** for the market.

### 1.2 `monitor` container

This is not a broad scanner anymore.

It no longer wastes effort on the full Stage 1 universe.
It now consumes the **Stage 2 shortlist**.

Its job is:

1. Wait for the latest same-day Stage 2 output
2. Start the tick collector only for the shortlisted names
3. Run live liquidity/tradability confirmation on those shortlisted names
4. Refresh when the Stage 2 shortlist changes

This is more efficient and more aligned with actual intraday execution.

Stage 1 may give `100-300` names.
Stage 2 may give `3-10` names.
Monitoring the `3-10` names is the right practical choice.

### 1.3 `market-data-gateway` container

This is the shared Dhan access lane for REST-style market-data calls.

Its job is:

1. Centralize data access
2. Reduce duplicated request logic across services
3. Provide one internal path for historical/intraday/quote/OHLC fetches
4. Create a clean future extension point for:
   - more request classes
   - caching
   - retries
   - later multi-account routing if needed

For now there is still only one Dhan user and one API key.
That is fine.
The gateway is still valuable even with one account because it centralizes behavior and removes direct Dhan access sprawl.

---

## 2. What Each Existing Stage Should Mean

### 2.1 Stage 1: Universe sanitation / daily baseline filter

This is a daily preparation stage.

Its job is not to find trades.
Its job is to remove names that are structurally bad candidates for intraday trading.

That means:

- surveillance filtering
- bad liquidity history filtering
- unusable price-band filtering
- historical quality filtering

Its output is the **daily tradeable universe**.

This output should be treated as a daily input artifact, not a live signal.

### 2.2 Stage 2: Momentum ignition scan

This is the true live opportunity scan.

Its job is:

- "out of today's clean universe, which names are beginning to move now with meaningful participation?"

The current implementation already reflects that well:

- RVOL
- VWAP position
- opening-range breakout
- volume acceleration

That means Stage 2 is the main **opportunity-generation stage**.

Its output is the **live shortlist**.

This shortlist is the most important stock-level output the system currently produces.

### 2.3 Monitor: Live tradability confirmation

Monitor is not a stock-selection stage.
It is a **live confirmation layer**.

Its job is:

- "these shortlisted names look interesting; are they still live, tradeable, and active enough right now?"

That means:

- tick activity
- live spread quality
- live RVOL confirmation
- shortlist refreshes as Stage 2 changes

Monitor should remain subordinate to Stage 2, not the other way around.

---

## 3. Regime Should Be Independent, Not Stage 3 in the Sorting Funnel

This is the most important architectural conclusion.

`regime` should not be modeled as the next numbered stage after Stage 2.

Why:

1. Stage 1 and Stage 2 are stock-sorting stages.
2. Regime is not sorting stocks.
3. Regime is classifying the **market environment**.
4. That is a different class of responsibility.

So the correct mental model is:

- `sorting` = stock universe + stock opportunity discovery
- `regime` = market context / permission / bias engine
- `monitor` = live confirmation

Regime belongs to the **control plane**, not the stock funnel.

### 3.1 Why regime must run independently

If regime runs after all stock sorting is complete, then the system does this:

1. spend effort narrowing 5300 stocks to a handful
2. only then discover "today is not tradable"

That is not ideal if regime is meant to control high-level participation, aggressiveness, and whether trading should even be active.

So regime should:

- start independently at market open
- observe early market structure
- produce its first meaningful classification after opening discovery

### 3.2 First actionable regime timing

Regime should start at market open, but its first reliable classification should not be instantaneous.

Recommended flow:

- `9:15 AM`: regime container starts collecting market-open data
- `9:35-9:45 AM`: first actionable regime classification
- later updates: slower cadence, for example every `60-120` minutes or fixed checkpoints

This matches the practical idea that:

- open is noisy
- regime becomes meaningful after the first block of discovery

### 3.3 Regime outputs should be operational, not only descriptive

Regime should not only output labels like:

- `trend`
- `mean_reversion`
- `choppy`
- `event`

It should also output structured control fields the rest of the system can use.

Recommended regime output fields:

- `market_regime`
- `regime_confidence`
- `trade_permission`
  - `allowed`
  - `reduced`
  - `blocked`
- `preferred_style`
  - `trend_following`
  - `mean_reversion`
  - `observer_only`
- `long_bias`
- `short_bias`
- `position_size_multiplier`
- `max_concurrent_positions`
- `next_review_at`
- `reasoning_summary`

This makes regime directly usable by downstream logic.

---

## 4. Future Architecture With AI Agents

The future system should not be thought of as "more stages."
It should be thought of as **specialized services and agents**.

### 4.1 Proposed top-level lanes

1. `sorting`
   - owns Stage 1 and Stage 2
   - produces daily universe and live shortlist

2. `regime`
   - owns market-context classification
   - independent of stock sorting
   - slower refresh cycle

3. `monitor`
   - tracks the Stage 2 shortlist in real time
   - confirms tradability and live activity

4. `market-data-gateway`
   - shared market-data access layer

5. `decision-agent` lane
   - future AI-driven decision layer
   - consumes:
     - Stage 2 shortlist
     - regime output
     - monitor output
     - possibly account/risk state

6. `execution-agent` lane
   - future trade-placement / order-management layer

### 4.2 Regime AI agent

Your idea here is strong.

There will be things the rules engine can measure numerically:

- index structure
- breadth
- volatility
- VWAP behavior
- sector participation

But there are also things it cannot understand deeply by itself:

- macro/news meaning
- policy tone
- whether news is bullish, bearish, or risk-off
- how serious an event is
- whether it changes market confidence versus only creating temporary noise

So the `regime` service should eventually include an AI news-analysis component.

That agent should:

1. read relevant market news
2. summarize it briefly
3. classify sentiment and market impact
4. return structured outputs that code can consume

Recommended AI news output schema:

- `headline_summary`
- `market_sentiment`
  - `bullish`
  - `bearish`
  - `mixed`
  - `neutral`
- `confidence_score`
- `event_severity`
- `affected_sectors`
- `risk_of_abnormal_volatility`
- `trade_caution_level`
- `structured_reasoning`

This output should not directly place trades.
It should become one input into the regime engine.

### 4.3 Intelligent decision agent

After `sorting`, `regime`, and `monitor` exist as strong structured services, a higher-level AI agent can combine them.

Its job should be:

- understand the shortlisted names
- understand the market regime
- understand live tradability confirmation
- understand whether the environment supports entries
- decide whether to:
  - act
  - wait
  - reduce aggression
  - skip trading

This agent should consume structured state, not raw uncontrolled logs.

That means the current architecture should keep moving toward:

- saved JSON contracts
- clearly defined outputs per service
- consistent schema between services

---

## 5. Recommended System Flow

### 5.1 Pre-market and market-open flow

1. Around `8:45 AM`
   - `sorting` runs Stage 1
   - creates the daily tradeable universe

2. `9:15 AM`
   - market opens
   - `sorting` starts Stage 2 loop on a 10-minute cadence
   - `regime` starts collecting opening market data

3. Around `9:35-9:45 AM`
   - `regime` publishes first meaningful regime snapshot

4. As Stage 2 outputs arrive
   - `monitor` consumes the Stage 2 shortlist
   - tick collector follows only those names
   - monitor confirms live quality

5. Later
   - decision layer consumes:
     - Stage 2 shortlist
     - monitor confirmation
     - regime state
     - news interpretation
   - then future execution layer acts

### 5.2 Why this flow is better

This structure avoids several mistakes:

- using monitor on too many useless names
- treating regime as just another stock-sorting stage
- letting one generic backend own unrelated responsibilities
- delaying market-context classification until after most work is already done

It also creates a clean future for AI agents:

- regime AI agent for news/context
- decision AI agent for trade-level synthesis
- execution AI agent for disciplined action

---

## 6. What Is Still Missing From the System

The system is already working meaningfully, but these higher-level pieces are still missing:

### 6.1 A shared session-state layer

Right now files are doing a lot of the coordination work.
That is useful and practical, but eventually the system should also expose a more explicit shared state, such as:

- current market regime
- trading enabled / reduced / blocked
- current Stage 2 shortlist version
- current monitor shortlist version
- current risk mode

### 6.2 A decision contract

The system currently finds and confirms opportunities.
It does not yet have a final authoritative layer that answers:

- trade this now
- wait
- skip
- reduce size

That is what the future decision agent should become.

### 6.3 A clear observer mode

Even on days when regime blocks trading, the rest of the system may still be valuable in observation mode for:

- logging
- validation
- model feedback
- post-market review

So "no trading" should not mean "turn off intelligence."
It should mean:

- keep observing
- do not act

---

## 7. Naming and Ownership Going Forward

### 7.1 Current service naming

Recommended names:

- `sorting`
- `monitor`
- `market-data-gateway`

Future:

- `regime`
- `decision-agent`
- `execution-agent`

### 7.2 Ownership model

- `sorting` owns:
  - Stage 1 creation
  - Stage 2 momentum loop

- `monitor` owns:
  - Stage 2 shortlist live confirmation
  - tick collection for shortlisted names

- `market-data-gateway` owns:
  - shared Dhan REST access

- `regime` will own:
  - market context
  - permissioning
  - market-news interpretation

This separation makes the system easier to reason about and easier to scale.

---

## 8. Final Architecture Statement

The system should no longer be viewed as a simple numbered chain.

It is better understood as:

1. **Sorting lane**
   - find clean and promising stocks

2. **Regime lane**
   - understand what kind of market day this is

3. **Monitor lane**
   - confirm whether shortlisted stocks remain live and tradeable

4. **Decision lane**
   - synthesize structured outputs into trade intent

5. **Execution lane**
   - place and manage trades safely

That is the clearest, most correct mental model for where the project is going.
