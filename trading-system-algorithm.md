Before the blueprints, one critical honesty check — then the most complete analysis possible.

No trading system can *guarantee* zero losses on every trade. That is mathematically impossible in any market. What we can engineer is a system with positive *expectancy* — meaning that across enough trades, the expected value of each rupee risked is positive, and the drawdown profile is so tightly controlled that the account grows month-over-month reliably. That is the real goal. Every design decision below is aimed at that.

Let's build it properly. Here is the full funnel from universe to execution

![alt text](image.png)

:Now the full reasoning, layer by layer.

---

## The foundational truth about edge

Before any code gets written, you need to understand what actually creates a repeatable edge in intraday BSE trading, because this determines every design decision downstream.

Your edge does not come from predicting stock movement. It comes from four compounding factors working together: trading only when conditions are asymmetric (the setup is high-probability), sizing positions correctly so no single loss is catastrophic, having a better exit process than your entry process, and being disciplined enough to take zero trades when conditions don't meet the bar. The system we're designing below is engineered to enforce all four of these automatically, because humans under the pressure of live markets consistently violate all four.

---

## Tier 1 in full detail — the continuous background engine

### Stage 1: Universe sanitation (the static daily filter)

This runs once pre-market at 8:15 AM and produces a clean tradeable universe. The key insight missing from all three analyses is that this isn't just a liquidity filter — it's a *risk sanitation* layer. You are not just asking "can I trade this?" You are asking "could this stock destroy my account if something unexpected happens?"

The exclusion list must include stocks on the ASM (Additional Surveillance Measure) and GSM (Graded Surveillance Measure) lists, which BSE publishes daily. These stocks have artificially constrained volumes and manipulated price action — they look liquid on some days and then freeze completely. This was only mentioned in Response 1 and it is critical. Additionally exclude any stock with a corporate action announced for today (ex-dividend, stock split, rights issue) because these cause extreme gap behavior and your historical volatility models will be calibrated on pre-event data that no longer applies. Also exclude any stock where the circuit limit was hit in the last 5 trading days — that is a signal of operator activity.

Price range filter: below ₹50 you get extreme spread costs that eat your edge, above ₹5000 your position sizing becomes coarse (you can only trade 1-2 lots meaningfully on a retail account). The practical sweet spot is ₹100–₹3000.

This stage should produce roughly 200–350 stocks from the original 5000.

### Stage 2: Hard liquidity gate (the intraday dynamic filter)

This runs every 10 minutes during market hours on the ~300 surviving stocks. The numbers from Response 2 (₹10 Crore ADV) are good starting thresholds, but the more important metric that none of the three analyses properly emphasised is *time-of-day volume normalisation*.

A stock that trades ₹2 Crore in the first 30 minutes is far more liquid than a stock that trades ₹2 Crore total but most of it in the last hour. You need to compute, for each stock, the rolling 10-day average volume at this specific time of day, and compare today's volume against that baseline. This is the Relative Volume (RVOL) metric. An RVOL above 1.5x at the current time means the stock is genuinely participating today.

The bid-ask spread check is not just about the quoted spread at this moment. You should compute the median effective spread over the last 50 ticks. A stock can show a ₹0.05 spread right now but average ₹0.30 over the last 10 minutes during fast market conditions. That median is what you'll actually pay on execution.

ATR% threshold of 1.5% minimum is correct. Below that, the stock simply doesn't move enough to generate a meaningful risk-reward trade after accounting for your entry and exit costs (spread + brokerage + STT + stamp duty). On BSE, total round-trip friction is approximately 0.15%–0.25% depending on trade size. Your ATR needs to be at least 6–8x your friction to have any edge.

This stage narrows to roughly 30–60 stocks.

### Stage 3: Momentum ignition scan (the dynamic filter)

This is where Response 2 was strongest and introduced the best framing. You are looking for "momentum ignition" — the specific moment a stock begins breaking out from a base with institutional participation.

The three signals that matter most in combination are: RVOL spike above 2x baseline (institutional money moving), price crossing above VWAP with increasing speed (direction confirmation), and opening range expansion (the stock is breaking its first 15-minute high/low range, which is the institutional entry signature on BSE). Any one of these signals is noise. All three together is a setup.

The improvement I'd add here, which none of the three analyses mentioned, is the *volume acceleration derivative*. This is not just "is volume high?" but "is volume growing at an accelerating rate?" A stock going from 50K shares/minute to 100K to 200K is a far stronger signal than a stock that jumped to 200K and stayed flat. The rate of change of volume is a leading indicator; the absolute volume level is a lagging one.

An important addition from Response 1 that the others missed: sector and broader market alignment. If Sensex is down 0.8% and you're about to go long on a stock that happens to show momentum, you're fighting the tide. Your regime detection layer (Stage 4) needs to include a market-direction filter that adjusts the long/short bias of what you're looking for.

This stage produces 5–15 stocks.

### Stage 4: Regime detection — the most important layer nobody builds first

This is an original improvement beyond all three analyses, and it is arguably the single most important component of the whole system. Here's why: most trading systems fail not because their signals are wrong, but because they apply trend-following signals on a mean-reversion day, or mean-reversion signals on a trend day. The regime is the context in which every other signal must be interpreted.

Classify each day into one of four regimes by 9:45 AM (after 30 minutes of price discovery), using the following logic applied to Sensex/Nifty intraday behavior:

A trend day is characterised by the index opening and moving in one direction with progressively higher lows (uptrend) or lower highs (downtrend), no significant retracement through VWAP, and India VIX stable or declining. On trend days, momentum signals are highly reliable, breakouts work, and you should run your winners hard. Don't take profits early.

A mean-reversion day is characterised by a gap open that immediately begins filling, price oscillating around VWAP throughout the session, and equal volume on both sides of the order book. On these days, breakouts fail. You want to fade moves away from VWAP, not chase them. The entire scoring model in Stage 3 needs to invert — what looks like momentum ignition is actually an overextension that will reverse.

An event day occurs when there's a major macro event (RBI rate decision, budget, election result, global market shock). On these days, all models based on historical volatility are invalid because realised volatility will be a multiple of the model's prediction. The correct response is to either reduce position size to 25% of normal or simply not trade at all. Response 1 described this correctly; the others didn't.

A choppy/random day has no consistent direction, low RVOL, and multiple VWAP crossings without follow-through. On these days, no trading system has reliable edge. The correct output from the system is "no trade available today."

The regime detection changes the weights in your Stage 3 scoring formula dynamically. On a trend day, momentum and breakout signals get 70% weight. On a mean-reversion day, VWAP deviation and order book imbalance get 70% weight instead.

### The champion scoring formula

This is the concrete mathematical implementation, which none of the three analyses provided:

`Score = (RVOL_score × regime_weight_1) + (VWAP_distance_score × regime_weight_2) + (spread_quality_score × 0.15) + (ATR_score × 0.10) + (sector_alignment × 0.10)`

Where each component is normalised 0–100 and regime weights shift based on the classified regime. This produces a single composite score. The top 1–3 stocks above a threshold of 65 are written to the champion cache with a 10-minute TTL in Redis.

---

## Tier 2 in full detail — the agent swarm

### The four agents, improved

The Technical Analyst agent from Response 2 is well-conceived but needs one critical addition: it must perform multi-timeframe confluence analysis, not just look at one chart. Specifically, the 15-minute chart must show the trend direction, the 5-minute chart must show the trigger setup (breakout, pullback to support, etc.), and the 1-minute chart must show the precise entry timing. A trade that has 15m trend + 5m setup + 1m entry alignment is a far higher-probability trade than any single-timeframe signal. This is a core principle of professional intraday trading that the analyses glossed over.

The Microstructure agent from Response 2 is the strongest differentiating component of the whole architecture. Reading the Level 2 order book for buy/sell imbalance is genuinely predictive at sub-5-minute horizons — it is the closest thing to a leading indicator that exists in equity markets. The improvement here: don't just look at the current snapshot of Level 2. Track how the order book has changed over the last 2–3 minutes. Specifically, large limit orders that are being added and then removed (spoofing behavior) should reduce your confidence. Large limit orders that are being steadily filled (genuine institutional buying) should increase it. The *dynamics* of the order book matter more than any single snapshot.

The Catalyst agent should do three specific things: check BSE's corporate announcement feed for any news in the last 4 hours specifically for this stock, check sector performance to confirm the stock is moving with its sector (sector rotation trade) rather than against it (possible idiosyncratic risk), and check FII/DII provisional data if available to confirm institutional direction. The news veto is important — if there is a headline that could explain the move but introduces binary outcome risk (a company pending an NCLT judgment, a stock near a court-ordered price, etc.), the correct response is to skip the trade entirely regardless of technical setup quality.

The Volatility agent is the most undervalued of the four. Its job is to answer one question precisely: given today's actual realised volatility for this stock, where should the stop loss be placed so that the market's normal noise doesn't hit it, but a genuine move against the trade does? The answer is the 1.5x ATR below the entry (for longs). This is not a rigid formula but a starting point — the agent must compare the 1.5x ATR stop to the nearest structural support level. The stop should sit just below the structural support, not just at 1.5x ATR. Whichever is tighter, but also defensible by market structure, wins.

### The Meta-Agent (CIO) — the improvement

Response 2 described this correctly but missed one crucial feature: the Meta-Agent should not just check if agents agree. It should also check *why* they agree and whether those reasons are independent. If the Technical Agent says "bullish" because the stock is above VWAP, and the Microstructure Agent says "bullish" because there's buy imbalance in the order book, those are genuinely independent signals. But if both are saying "bullish" because the stock just gapped up 2%, they are both reacting to the same underlying event — that's not confluence, that's correlation. The Meta-Agent needs to evaluate signal independence.

The output of the Meta-Agent should be a structured JSON that includes: direction (long/short/none), confidence score (0–100), the specific reasons for the trade, the specific reasons against, the single most important risk, the entry price, stop loss, two targets (50% at T1, let remainder run to T2), and time stop (maximum 2 hours, after which the trade is closed regardless of P&L if it hasn't hit stop or target).

---

## The risk architecture — the true source of consistent returns

This is the section where the system either succeeds or fails at a deep level, and it requires more attention than any of the three analyses gave it.

The core insight is this: consistent monthly returns come not from having a high win rate, but from having asymmetric trades. A system that wins 45% of the time but makes 3x what it loses on winners versus losers will outperform a system that wins 65% of the time but makes equal amounts on wins and losses. The math works out to: 45% × 3R − 55% × 1R = 1.35R − 0.55R = 0.80R positive expectancy per trade. At 4 trades per week, that's roughly 3.2R per week in expected value. If each R (risk unit) is 0.5% of account, that's 1.6% per week, compounding to roughly 6–8% per month — without needing to be right more than half the time.

This means the most important number in your system is not accuracy. It is the reward-to-risk ratio enforcement. The risk gate must hard-reject any trade where the measured RR (distance to T1 divided by distance to stop) is below 1.8. No exceptions.

Per-trade risk: 0.3%–0.5% of account equity per trade. This is deliberately conservative. At 0.5% risk per trade with a maximum of 3 concurrent positions, your maximum theoretical simultaneous risk exposure is 1.5% of equity. If all three hit stop simultaneously (which would require highly correlated stocks moving together, which your sector correlation check prevents), you lose 1.5% in a single day. Your daily loss limit is 1.5% — that's your kill switch.

The daily kill switch is non-negotiable and must be implemented at the code level, not as a guideline. When daily P&L hits −1.5%, all open positions are closed, no new orders are placed for the rest of the session, and the system enters "observer mode" — it continues running Tier 1 and logging what it would have done, but takes no action. This serves a second purpose: it lets you study what the system does on bad days without costing you money.

Monthly stop: if the account drawdown from the monthly high-water mark exceeds 4%, reduce position size to 50% for the remainder of the month. If it reaches 6%, stop trading for the rest of the month. These numbers sound conservative — they are. A system that earns 4% in good months and loses 1% in bad months has a better Sharpe ratio than a system that earns 8% in good months and loses 5% in bad months, even though the latter has higher peak returns.

---

## The improvement none of the three analyses included: the feedback loop

The biggest missing piece in all three analyses is the continuous learning loop that makes the system better over time. Here's how to implement it:

Every trade the system takes — whether it wins or loses — gets logged to a database with every signal value at the time of entry. The champion score, the RVOL, the order book imbalance, the confidence level, the regime tag, the sector that day, everything. After 4 weeks of live trading (or paper trading), you run a simple feature importance analysis to answer: which signals actually predicted outcomes, and which were noise? You will almost certainly find that 2–3 signals dominate and the rest add little predictive value. You then increase the weight of the predictive signals and reduce or remove the others.

This iterative calibration is what separates a system that works in backtest from one that works in live markets. Market microstructure on BSE shifts seasonally, changes with market cap and volatility regime, and drifts over time. A static model degrades. A model that reweights itself every month based on recent performance stays sharp.

---

## The implementation roadmap — honest and phased

Phase 1 (weeks 1–4): Build the Tier 1 scanner with purely rule-based filters — no ML, no AI. Run it in observation mode only. Log every candidate stock and what would have happened if you traded it. This is your ground truth dataset for calibrating everything that follows, and it also tells you whether your data pipeline is functioning correctly with no look-ahead bias.

Phase 2 (weeks 5–8): Build the agent swarm framework with hard-coded rules for each agent. Implement the risk gate and paper trade with real-time data. Measure expectancy, profit factor, and regime-wise performance. Do not go live until paper trading shows at least 30 trades with positive expectancy.

Phase 3 (weeks 9–12): Introduce probabilistic scoring in the champion selection. Add the feedback logging system. Begin live trading at 25% of intended position size. Watch for slippage discrepancy between paper and live (this is where most systems break — they assume paper prices but get filled 0.1%–0.3% worse live, which can flip a marginally profitable system to unprofitable).

Phase 4 (month 4 onward): Full position sizing. Monthly model recalibration. Regime-wise performance review. Gradual expansion toward 2–3 concurrent trades.

---

## The metrics that actually tell you if the system is working

Track these, in order of importance: expectancy (average rupee gained per rupee risked, must be positive), profit factor (gross profit divided by gross loss, must be above 1.5), maximum consecutive losses (never let this exceed 5 in a row without pausing to diagnose), regime-wise win rate (the system must perform differently in different regimes — if it doesn't, your regime detection isn't working), Tier 1 alpha (how often did the top-ranked stock from Tier 1 become the actual best opportunity that day — this is your scanner quality metric), and slippage drift (the difference between theoretical entry and actual fill, tracked as a rolling average — if this grows over time, your execution is degrading).

Win rate is listed last deliberately. A system with 40% win rate and 2.5R average winner is a better system than one with 60% win rate and 0.8R average winner. Focus on asymmetry, not accuracy.

The system described above, executed with discipline, should produce 4–8% monthly returns on the trading capital with a maximum monthly drawdown kept under 4–5%. That is the realistic target. "Never making a loss on a single trade" is not the goal — making enough on winners and losing little enough on losers that the account grows steadily every month is.

