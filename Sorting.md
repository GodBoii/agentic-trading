### **PHASE 1: Stock Selection/Filtering Agent**

**Current Gap:** You need robust criteria here. Suggestions:

**Liquidity Filters (Critical for Scalping):**
- Average Daily Volume > 500K shares
- Average Daily Turnover > ₹10 crores
- Bid-Ask Spread < 0.1% (tight spreads essential for scalping)
- Market depth (top 5 bids/asks should have substantial volume)

**Volatility Filters:**
- ATR (Average True Range) % between 2-5% (sweet spot for intraday)
- Bollinger Band width analysis
- Historical Intraday Range (HIR) > certain threshold

**Trend & Momentum Filters:**
- Stock above 20, 50, 200 EMA for long bias (or below for short)
- RSI between 40-60 (not overbought/oversold at open)
- Volume surge detection (today's volume > 1.5x of 10-day avg)

**Sector & Market Correlation:**
- Filter by sector momentum (which sectors are hot today?)
- Beta to Nifty50 (for understanding market correlation)
- Eliminate stocks with earnings/events scheduled that day

**Practical Algorithm:**
```
1. Universe: Nifty 200 or 500 (liquid stocks)
2. Apply liquidity filters → ~100-150 stocks
3. Apply volatility filters → ~30-50 stocks
4. Apply momentum/trend filters → ~10-20 stocks
5. Rank by composite score → Top 3-5 stocks
6. Final LLM review of news/events → Pick 1-2 stocks
```

## **1. Stock Sorting & Selection Agent**

**Objective**: Filter 2000+ NSE/BSE stocks to identify the most promising candidates for intraday trading.

**Implementation Framework**:
- **Multi-stage filtering pipeline**:
  1. **Liquidity Screen**: Filter by average daily turnover (> ₹50Cr) and volume (> 500,000 shares)
  2. **Volatility Screen**: Calculate Average True Range (ATR) and historical volatility - target stocks with 2-5% daily movement
  3. **Momentum Pre-screening**: Use short-term momentum indicators (5-day ROC, gap analysis)
  4. **Sector Rotation Analysis**: Identify sectors showing relative strength using sector ETF analysis

**Specific Methods**:
- **Momentum Scoring**: Combine 5-day, 20-day returns with volume surge detection
- **Mean Reversion Potential**: Identify stocks trading >2 standard deviations from their 20-day moving average
- **Opening Range Breakout Candidates**: Pre-market analysis to identify stocks likely to break their opening range
- **News Catalyst Screening**: Flag stocks with earnings announcements, corporate actions

