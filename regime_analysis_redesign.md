# Regime Analysis Redesign

This document describes the redesigned regime analysis system. The implementation target is a single unified `REGIME_ANALYSIS_AGENT` using `mimo-v2.5-pro`.

## Current Problem

The old regime lane had two unequal parts:

- A deterministic/manual classifier that computed the final `market_regime`.
- A news agent that produced contextual prose.

That made the LLM branch mostly decorative. The news output could explain context, but it did not produce the final regime decision or structured downstream controls.

The redesign keeps deterministic calculations, but only as feature extraction. The final regime decision should come from one unified agent that sees all supplied evidence.

## New Architecture

The regime flow should be:

1. Resolve Indian market sources.
2. Fetch primary indices, sector indices, futures, and option chains.
3. Fetch market news, disclosures, and institutional flow.
4. Fetch global context from Alpha Vantage where available.
5. Build deterministic/manual feature metrics.
6. Build one `regime_packet`.
7. Run `REGIME_ANALYSIS_AGENT`.
8. Normalize the structured agent output.
9. Save `regime_latest.json` and `regime-{market_date}.json`.

The old deterministic classifier is now a feature/fallback engine. It should not be treated as the primary final decision when the unified agent succeeds.

## Agent Inputs

The unified agent receives:

- Indian market timing:
  - `market_timezone`,
  - `market_date`,
  - `generated_at_ist`,
  - source/event/fetch times converted to IST where available.
- Indian primary indices: Nifty 50, Sensex, Bank Nifty, India VIX.
- Sector indices.
- Index futures.
- Option-chain summaries.
- Deterministic feature metrics:
  - primary index change,
  - VWAP relation,
  - primary breadth,
  - sector breadth,
  - futures alignment,
  - VIX change,
  - opening range behavior,
  - PCR,
  - IV spread,
  - institutional flow diagnostics.
- News and disclosures:
  - BSE announcements,
  - Kotak news fallback,
  - Alpha Vantage news sentiment where available.
- Institutional flow:
  - current flow source if available,
  - stale flow explicitly marked as stale.
- Global context:
  - Japan/Nikkei 225,
  - Hong Kong/Hang Seng,
  - China/Shanghai Composite,
  - SGX/GIFT Nifty if available,
  - US S&P 500 and Nasdaq proxies if available,
  - USD/INR,
  - crude oil,
  - gold/silver.
- Data quality:
  - source,
  - fetch status,
  - fallback flag,
  - as-of time,
  - staleness seconds.

## Alpha Vantage Usage

The API key must come only from `ALPHA_VANTAGE_API_KEY`. It must not be hardcoded.

Useful Alpha Vantage functions:

- `NEWS_SENTIMENT`: global market news and sentiment. Useful topics: `financial_markets`, `economy_macro`, `economy_monetary`, `economy_fiscal`, `energy_transportation`, `finance`, `manufacturing`, `technology`.
- `MARKET_STATUS`: whether global markets are open or closed.
- `GLOBAL_QUOTE`: best-effort quote fetch for supported symbols.
- `SYMBOL_SEARCH`: symbol validation when adding new global instruments.
- `CURRENCY_EXCHANGE_RATE`: USD/INR, USD/JPY, USD/CNY.
- `BRENT` and `WTI`: crude context.
- `GOLD_SILVER_SPOT`: risk-off precious metals context.

Some global index endpoints may be premium or unsupported. The collector must mark unavailable sources and continue.

## Agent Output

The agent returns one JSON-compatible decision:

```json
{
  "market_regime": "choppy",
  "index_regime": "mean_reversion",
  "breadth_regime": "mixed_breadth",
  "volatility_regime": "normal_volatility",
  "flow_regime": "balanced",
  "event_regime": "none",
  "global_context_regime": "neutral",
  "confidence": 62.5,
  "is_actionable": true,
  "new_trade_permission": "reduced",
  "participation_bias": "selective",
  "max_position_size_multiplier": 0.5,
  "allowed_setup_types": ["stock_specific_momentum", "vwap_reclaim"],
  "avoid_setup_types": ["low_liquidity_breakout", "late_chase"],
  "risk_flags": ["mixed_sector_breadth"],
  "source_staleness": {},
  "reasoning_summary": "",
  "human_readable_report": ""
}
```

Downstream agents should continue receiving backward-compatible fields:

- `market_regime`
- `confidence`
- `status`
- `minutes_since_open`
- `is_actionable`
- `reasoning_summary`
- `diagnostics`
- `news_analysis`

New structured controls should be added inside the existing `regime` object rather than replacing the old shape abruptly.

## Agent Rules

The agent must:

- Use only supplied data.
- Use IST/Indian market time for market-session reasoning. UTC is retained only for audit and storage.
- Treat deterministic/manual labels as features, not binding decisions.
- Distinguish current data from stale or fallback data.
- Never treat stale FII/DII flow as today's live flow.
- Separate systemic news from isolated company news.
- Separate Indian market internals from global context.
- Avoid stock-specific trade recommendations.
- Provide regime controls useful for stock analyzer and executioner.

## Fallback

If the unified agent fails or returns invalid JSON, the system should save a degraded regime payload using deterministic features.

The fallback payload must clearly mark:

- `decision_source: deterministic_feature_fallback`
- `agent_error`
- reduced confidence or reduced trade permission where appropriate.

The regime loop should not crash solely because the LLM or Alpha Vantage fails.
