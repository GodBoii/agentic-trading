Before answering, let me read the regime-related files to understand what you currently have.Now I have a complete picture. Let me give you a structured, actionable improvement plan.

---

## Regime System: What You Have vs What It Should Be

### The Core Problem

Your regime system has two very unequal halves. The **deterministic branch** (price, breadth, futures, options, VIX — the part you haven't shared but is referenced throughout) is doing the heavy lifting and actually drives the `market_regime` label. The **news/LLM branch** is largely decorative — it produces a markdown report that downstream agents are explicitly told to ignore as "background only." The result from the live run confirmed this: `market_regime: mean_reversion` came from the deterministic branch, while the news branch said `sentiment: bearish` — and the whole pipeline correctly ignored that bearish label and traded anyway.

The improvement opportunity is not "make the LLM write better markdown." It's **make the news branch feed actionable structured signals back into regime classification**, not just produce prose the pipeline ignores.

---

### Issue 1: Data Sources Are Thin and Stale

**What you currently collect:**
- BSE mobile corporates page (corporate announcements, results, actions, offers, listings)
- Kotak Neo news page (scraped HTML headlines, no timestamps)
- Kotak Neo FII/DII page — but it gives **previous day's data**, not today's

**The FII/DII staleness problem is serious.** In your live run, the FII/DII data was from 27-May-2026 but the trading day was 29-May-2026. The regime system reported `flow_context: net_supportive` based on two-day-old data. On the actual trading day, FII flows were unknown.

**What to add:**

NSE India publishes provisional FII/DII data during market hours — it's available at `https://www.nseindia.com/api/fiidiiTradeReact` as a JSON API with today's buy/sell values updated intraday. This is the real-time source you need. Scraping Kotak for yesterday's data should be a fallback, not primary.

For news, BSE's official announcement feed is actually available as a proper JSON API at `https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w` with filters for date and category — much cleaner than scraping the mobile HTML. The mobile scraper is fragile (your regex on `<td id="tdDet">` will break on any BSE HTML update).

India VIX live data is available from NSE's API endpoint during market hours. Your regime loop runs on a schedule — if it runs at 10:40 it should be reading live VIX, not stale.

---

### Issue 2: Heuristic Sentiment Analysis Is Naive

Your `analyze_with_heuristics` method does keyword matching:

```python
positive_terms = {"rally", "surge", "gain", "strong", "beats", "approval", "record high", "dividend"}
negative_terms = {"fall", "selloff", "decline", "fraud", "loss", "misses", "default", "downgrade"}
```

This has several problems. "Loss" as a negative term will flag "Ramco Cements reports Q4 profit, narrowing loss from prior year" as bearish. "Order" as a keyword (weight 0.18 in the prioritizer) would fire on "Court order against company" and "Company wins ₹500cr order" equally. "Default" is flagged severe, but "Default settings retained" in a tech announcement would also trigger it.

The heuristic's confidence formula is `0.25 + (min(len(rows), 20) * 0.03)` — meaning with 20 headlines it caps at 0.85 confidence regardless of whether the headlines are saying anything meaningful. You're reporting high confidence on fundamentally noisy text matching.

**What to do instead:** The LLM agent already exists for the quality analysis. The heuristic should only serve as a **fast fallback** when the LLM call fails or times out, and it should be honest about its low confidence. The current code runs heuristics AND the LLM, then merges them via `agno_markdown_plus_heuristic` — but the merge logic takes heuristic scores and overwrites them with LLM text. Make the separation cleaner: LLM runs first, heuristic is pure fallback.

---

### Issue 3: The LLM News Agent Produces Prose, Not Signals

The `RegimeNewsAnalyzerAgent` returns `{"llm_markdown_analysis": "## Headline Summary\n..."}` — a markdown string. The downstream regime orchestrator takes this and puts it in the news_analysis blob, but the **regime label itself** (`market_regime: mean_reversion`) does not incorporate anything from the news analysis.

The news agent needs to return structured signals, not prose. Specifically, the regime classification should consider:

```python
# News signals that should shift regime label:
{
  "systemic_risk_flag": bool,        # fraud/default/regulatory action on a large-cap
  "event_driven_flag": bool,         # budget, RBI policy, election results today
  "sector_rotation_signal": str,     # e.g. "banking_outflow", "pharma_inflow"
  "broad_selloff_risk": float,       # 0-1, based on news + FII + VIX together
  "pre_event_caution": bool,         # scheduled event today (RBI, Fed, expiry)
}
```

These should feed into the deterministic regime classifier as modifiers, not sit in a separate markdown field that agents ignore.

---

### Issue 4: One Regime Label Is Insufficient

You have a single `market_regime` field: `mean_reversion`, `trending_up`, `trending_down`, `volatile`, etc. But intraday Indian markets have **layers** of regime that matter independently:

- **Index regime**: what Nifty50/Sensex is doing (the current `market_regime`)
- **Breadth regime**: how many stocks are participating (your `sector_breadth_ratio: 0.4` — only 40% of sectors moving together, which is telling)
- **Volatility regime**: VIX state — is it elevated, compressed, expanding
- **Flow regime**: institutional positioning — net buyer/seller, pace of flow
- **Event regime**: is there a scheduled event today that changes everything (RBI, expiry, budget, FOMC)

In your live run, `market_regime: mean_reversion` with `sector_breadth_ratio: 0.4` means "index is range-bound but most sectors aren't participating." That's important context for the stock-analyzer but it gets compressed into one label. The stock analyzer should know whether the mean-reversion is index-level-only (breadth low = most stocks are moving on their own) vs broad-based.

**What to add:** Separate `index_regime`, `breadth_regime`, and `volatility_regime` as three distinct fields in the regime output. The single `market_regime` becomes a composite label derived from all three.

---

### Issue 5: The Regime Loop Schedule Is Fixed, Not Event-Aware

`run_regime_loop.py` runs on fixed schedule times (`regime_schedule_times`). The regime is recalculated at those fixed slots regardless of what's happening in the market.

This means if a major event happens at 10:05 (like the Emmvee breakout, or a circuit filter on a large-cap, or an RBI announcement), the regime label used for the 10:40 trading run is still from the last scheduled slot — it doesn't reflect the 10:05 market state.

**What to add:** An event-triggered regime refresh. When the stock analyzer or surveillance service detects something materially unusual — RVOL > 5× across 3+ stocks, VIX spike > 5% intraday, a large-cap hitting upper/lower circuit — it should be able to request an on-demand regime refresh. The current architecture already supports this pattern (the orchestrator polls for requests via `ai_trading_request_path`), the same mechanism could work for regime.

---

### Issue 6: No Regime History or Transition Tracking

Each regime run produces a fresh snapshot but there's no tracking of **how the regime is changing** through the session. At 10:40 you know the current regime is `mean_reversion` but you don't know:
- Was it `trending_up` at 09:30 and transitioned?
- How long has it been in mean_reversion?
- Is it transitioning toward something else (rising VIX, deteriorating breadth)?

**What to add:** A simple intraday regime transition log. Each run appends to a `regime_intraday_log` with timestamp + label + key diagnostics. The stock analyzer and executioner can then receive not just the current regime but the trajectory — "mean_reversion stable for 60 min" vs "just transitioned from trending_up 15 min ago" are very different contexts for a breakout trade.

---

### Concrete Improvements, Prioritized

**Priority 1 — Fix data quality (highest impact, no ML needed):**
Replace Kotak FII/DII scraping with NSE's intraday provisional FII/DII API. Add a live India VIX fetch during market hours. Replace BSE mobile HTML scraping with the BSE JSON announcement API. These give the LLM agent and heuristics better raw material to work with.

**Priority 2 — Make news agent return structured signals:**
Change `RegimeNewsAnalyzerAgent.analyze()` to return a JSON object alongside the markdown, specifically these fields: `systemic_risk_flag`, `event_driven_flag`, `broad_selloff_risk (0-1)`, `pre_event_caution`. Feed these as modifiers into the regime classifier. One concrete example: if `broad_selloff_risk > 0.7`, the regime output should add a `caution_modifier` that the executioner *does* respect (unlike the current news prose).

**Priority 3 — Add breadth and volatility as separate regime dimensions:**
Expose `index_regime`, `breadth_regime`, and `volatility_regime` separately. The stock analyzer currently gets `market_regime: mean_reversion` which conflates all three. With separate dimensions it can reason: "index is mean-reverting but breadth is low (isolated moves) and volatility is compressed (BB squeeze imminent)" — which is exactly the Emmvee setup and would've gotten a more precise read.

**Priority 4 — Add regime transition tracking:**
Write each regime cycle's output to an intraday log file. Pass the last 3 regime snapshots to the stock analyzer and risk analyzer so they can see the trajectory, not just the current state.

**Priority 5 — Event calendar integration:**
Add a simple pre-market check: is today an RBI MPC date, an F&O expiry, a Union Budget date, or a US FOMC date? These are all predictable from a calendar. If yes, set `pre_event_caution: true` in the regime output and have the executioner reduce position size (or skip) automatically. This is a one-time build that protects against the biggest known risk days.

---

The fundamental shift to make is: **regime should produce structured decision inputs, not descriptive prose.** The news agent's markdown is useful for a human reading the logs, but the pipeline agents need numbers and booleans they can act on. Right now the regime system informs but doesn't constrain — making it produce actionable structured signals that actually feed into the execution decision is where the real improvement lies.


MetaTrader (MT4 / MT5)
Moomoo
Merrill
MarketSmith


If you're trading the Indian stock market (NSE/BSE opens at **9:15 AM IST**), several Asian markets open earlier and are often used as leading indicators for the Indian session.

| Market                                     | Opens (IST) |             |
| ------------------------------------------ | ----------- | ----------- |
| Tokyo Stock Exchange (Japan)               | ~5:30 AM    |             |
| Australian Securities Exchange (Australia) | ~5:30 AM    |             |
| Korea Exchange                             | ~5:30 AM    |             |
| Taiwan Stock Exchange                      | ~6:30 AM    |             |
| Hong Kong Stock Exchange                   | ~6:45 AM    |             |
| Shanghai Stock Exchange                    | ~7:00 AM    |             |
| National Stock Exchange of India           | 9:15 AM     | ([Dhan][1]) |

For an AI trading system focused on Indian equities, traders commonly monitor:

1. **Japan (Nikkei 225)** — first major Asian market to open.
2. **Hong Kong (Hang Seng)** — strong indicator of Asian risk sentiment.
3. **China (Shanghai Composite)** — important for metals, commodities, and global growth expectations.
4. **SGX GIFT Nifty** — arguably the most important leading indicator for NSE opening direction. It trades before the Indian cash market and is widely used to estimate the likely Nifty open.

If your goal is to predict the NSE opening move, a useful feature set is:

```text
Nikkei 225 overnight return
+
Hang Seng pre-open return
+
Shanghai early session return
+
US S&P 500 close
+
Nasdaq close
+
GIFT Nifty live change
+
Global news sentiment
```

That combination usually provides much more predictive value for the Indian open than looking at Indian historical prices alone.

[1]: https://dhan.co/blog/news/world-stock-market-timings-as-per-ist/?utm_source=chatgpt.com "World Stock Market timing as per Indian Time (IST)"


Welcome to Alpha Vantage! Your API key is: HNK70ASIHD5AF074. Please record this API key at a safe place for future data access.

https://www.alphavantage.co/documentation/#intelligence

https://www.alphavantage.co/documentation/
