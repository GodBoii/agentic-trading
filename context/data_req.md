# Universal / Market data (applies to all trading)

* **Time-series price data**

  * Open, High, Low, Close (OHLC) at various intervals (tick, 1s, 1m, 5m, 15m, 1h, daily)
  * Last trade price / mid price
* **Volume data**

  * Trade volume by bar
  * Tick-level trade sizes (time & sales)
* **Bid / Ask / Spread**

  * Best bid/ask (top of book), quoted spread
  * Bid/ask sizes (depth at top)
* **Order book / Level-2 / Market-Depth**

  * Multiple price levels (DOM)
  * Queue sizes, order placement/cancellation events
* **Time & Sales (tape)**

  * Each trade record: timestamp, price, size, aggressor side if available
* **Historical tick data** (for backtests that require realistic microstructure)
* **Corporate actions / corporate events**

  * Splits, dividends, spin-offs, mergers, buybacks
* **Exchange metadata**

  * Trading hours, tick size, lot size, trading calendars (holidays)
* **Reference data**

  * Ticker mappings, exchange codes, instrument identifiers (ISIN, FIGI)
* **Quotes history / snapshots** (book state saved periodically)

# Scalping / High-frequency specific

* **Ultra high-frequency tick data** (sub-second or tick)
* **Full order book (deep levels) and updates** (every update)
* **Order flow metrics**

  * Aggressor buys vs sells, trade-type classification
  * Imbalance (bid vs ask volume) and delta
* **Time-and-sales with millisecond timestamps**
* **Latency & timestamps**

  * Precise timestamping, clock sync (NTP/PPS)
* **Market microstructure metrics**

  * Quote update rates, order cancellations, iceberg detection
* **Real-time spread & effective spread monitoring**
* **Depth charts / DOM snapshots** for execution decisions
* **Exchange / broker execution reports** (fill times, ACKs)
* **Transaction costs & slippage statistics**
* **Tape-derived indicators**

  * Volume profile, footprint charts, VWAP per minute/second
* **Connectivity/market venue metrics**

  * Route latency, order rejection rates, throttling info

# Futures-specific data

* **Contract specs**

  * Contract size, tick size, tick value, margin multiplier, exchange code
* **Expiry / roll info**

  * Expiration dates, first notice / last trade day, rollover conventions
* **Settlement prices**

  * Daily settlement, final settlement method (cash/delivery)
* **Open interest (OI)**

  * OI by contract, change in OI
* **Futures term structure**

  * Prices across maturities, calendar spreads, contango/backwardation
* **Basis and basis history**

  * Futures price − spot price (basis), carry cost
* **Delivery / physical/financial settlement data**
* **Margin requirements / maintenance margin**
* **Position limits and reporting**
* **Exchange clearing & fees**
* **Historical continuous futures series** (properly rolled, adjusted)
* **Volume by contract (monthly/expiry)**
* **Settlement/auction prints**

# Options-specific data

* **Option chain data**

  * All strikes and expiries with bids/asks, last trade, sizes
* **Implied volatility (IV)**

  * IV per strike/expiry, IV surface (strike, expiry)
* **Greeks**

  * Delta, Gamma, Theta, Vega, Rho (per option)
* **Option volume & open interest by option**
* **Bid/ask spreads / liquidity measures for each option**
* **IV skew / smile metrics**

  * Put/Call skew, skew slope
* **IV term structure**

  * IV vs expiry, term structure plots
* **Model inputs**

  * Underlying price, interest rates, dividends, realized vol
* **Historical option prices** (for backtests)
* **Early exercise / American vs European style rules**
* **Assignment / exercise history / notices**
* **Option chains with tick history** (time & sales for options)
* **Synthetic positions & replication data**

  * Futures vs options parity checks
* **Volatility indices and proxies** (e.g., VIX for indices)

# Macro, economic & fundamental data (helps directional and options/futures strategy)

* **Economic calendar**

  * NFP, CPI, GDP, rate decisions, employment reports (actual, forecast, previous)
* **Interest rates / yield curves**

  * Short and long rates, repo rates, risk-free curve
* **FX rates** (if underlying or hedging across currencies)
* **Macro indicators**

  * PMI, consumer sentiment, trade balance, central bank statements
* **Company fundamentals** (for single-stock futures/options)

  * Earnings dates, EPS, revenue, guidance
* **Dividends and ex-dividend dates** (impact on options)
* **Credit spreads / CDS** (for corporate sensitivity)

# News, sentiment & alternative data

* **Real-time news feeds**

  * Headlines, company announcements, exchange notices
* **News sentiment / NLP signals**

  * Aggregated sentiment scores, topic tagging
* **Social media / alternative sentiment**

  * Twitter, Reddit, newswire sentiment indices
* **Event data**

  * M&A rumors, earnings surprises, regulatory filings
* **Web traffic, app usage, satellite / footfall, supply chain data** (alt datasets)
* **Search trends / Google Trends**

# Risk, account & broker data

* **Account balances / margin utilization**
* **Positions (real-time)**

  * Net and gross exposures per instrument
* **Realized & unrealized P&L**
* **Leverage limits, buying power**
* **Order fills & execution quality reports**

  * Fill price, size, timestamp, venue
* **Commission & fee schedules**
* **Trade logs / audit trails**
* **Risk limits / stop rules**

# Derived / analytics data to compute from raw data

* **Volatility measures**

  * Historical volatility (realized), rolling vol, intraday vol
* **Liquidity metrics**

  * ADV (average daily volume), depth, market impact estimates
* **Slippage & transaction cost models**
* **Correlation and covariance matrices**

  * Cross-asset and cross-instrument correlations
* **Performance metrics**

  * Sharpe, Sortino, max drawdown, expectancy, win/loss ratio
* **Position sizing inputs**

  * Volatility-based sizing, Kelly, fixed fractional
* **Scenario / stress test data**

  * Tail risk simulations, VaR, expected shortfall
* **Predictor features**

  * RSI, MACD, moving averages, momentum, mean reversion signals
* **Seasonality & calendar effects**

  * Hour-of-day, day-of-week, monthly seasonality

# Data quality, engineering & metadata

* **Timestamp fidelity & timezone**

  * Millisecond precision, timezone normalization
* **Missing data / null handling**
* **Survivorship bias checks**

  * Delisted instruments, survivorship-free histories
* **Corporate action adjustments**

  * Adjust OHLC for splits/dividends
* **Data lineage & provenance**

  * Source, collection time, delays, licensing
* **Storage & retention**

  * Compressed tick store, rolling archives, fast cache for live
* **Backtest realism**

  * Order queue simulation, fill models, realistic latency

# Practical checklist by strategy (minimal vs recommended)

* **Scalping (minimal)**

  * Tick data, Level-2, time & sales, top-of-book sizes, latency metrics, execution reports, commission & slippage model
* **Intraday / swing futures (minimal)**

  * 1m/5m OHLC, volume, open interest, settlement prices, term structure, economic calendar
* **Options strategies (minimal)**

  * Full option chain (bids/asks), IV per strike/expiry, Greeks, underlying spot, dividends, interest rate, option volume & OI
* **Robust hedge/perf analysis (recommended)**

  * Historical option ticks, IV surface, realized vol history, scenario P&L grid, assignment history

# Sources & delivery types (where to get data)

* **Exchange feeds** (direct, paid)
* **Brokers’ APIs / market data bundles**
* **Data vendors** (TickData, QuantHouse, Bloomberg, Refinitiv, etc.)
* **Public APIs** (for equity fundamentals, macro calendars)
* **News providers / NLP vendors**
* **In-house instrumentation** (for execution metrics & latency)

---

