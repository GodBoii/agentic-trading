# The Two-Tier Agentic Trading Architecture

Building an autonomous AI trading system for the BSE (Bombay Stock Exchange) requires decoupling the **Discover phase** from the **Action phase**. By breaking this into a Continuous Background Scanner (Tier 1) and a User-Triggered Agentic Swarm (Tier 2), you ensure the AI does not waste compute cycles analyzing bad setups, and when the user clicks "Start Trading," the system is analyzing the absolute best candidate available at that exact second.

---

## Tier 1: The Continuous Sorting Engine (Background Process)
**State**: Runs headlessly on a schedule (e.g., every 1 to 5 minutes) via a cron job or Celery worker. 
**Goal**: Sieve through the 5000+ BSE stocks and isolate exactly **ONE** champion stock.

### Step 1.1: Pre-Market Filtration (The Static Filter)
*Time: Pre-Market (8:00 AM - 9:00 AM)*
Out of 5000 stocks on BSE, roughly 80% are illiquid, penny stocks, or subject to operator manipulation. We need a "Tradeable Universe".
- **Liquidity Filter**: Average Daily Volume over the last 10 days must be > ₹10 Crores.
- **Volatility Filter**: Average True Range (ATR%) > 1.5%. Dead stocks don't yield intraday profits.
- **Price Filter**: Remove penny stocks (Price < ₹50) and overly expensive stocks avoiding retail spread (Price > ₹5000).
- **Result**: A refined list of roughly 250 highly liquid, safe, and active stocks.

### Step 1.2: Real-Time Momentum Scanning (The Dynamic Filter)
*Time: Market Hours (9:15 AM - 3:30 PM)*
Fetch live WebSocket data for the 250 stocks. We are looking for **Momentum Ignition**—the exact moment a stock starts breaking out.
- **Relative Volume (RVOL) Spike**: Is the volume right now unusually high compared to the 10-day average for this specific time of day?
- **VWAP Positioning**: For a long trade, Current Price > Intraday VWAP. 
- **Regime Context**: Is the broader market (BSE Sensex/Nifty) supporting this move, or is it going against the grain?
- **Result**: An "Active Watchlist" of roughly 3 to 5 stocks.

### Step 1.3: The Champion Selection (The Scoring Engine)
Mathematically rank the 3 to 5 stocks to pick the ultimate winner.
- Calculate a composite score based on: Bid-Ask Spread tightness, Volume Acceleration, and distance from VWAP.
- **Result**: The #1 Stock (e.g., `RELIANCE`). This ticker is saved dynamically in a fast cache (like Redis) under a key: `CURRENT_CHAMPION_STOCK`.

---

## Tier 2: The Agentic Analysis Swarm (User-Triggered)
**State**: Triggered instantly when the user clicks "Start Trading" in the UI.
**Goal**: Pull the `CURRENT_CHAMPION_STOCK`, perform exhaustive multi-dimensional analysis, predict the trade direction, calculate risk, and execute.

When the trigger fires, the system initiates an **Agent Swarm** utilizing frameworks like Agno/LangChain. Individual AI agents simulate a team of hedge fund experts analyzing the champion stock simultaneously.

### Agent 1: The Technical Analyst (TA)
- **Role**: Understands chart geometry and indicators.
- **Inputs**: 1m, 5m, and 15m candlestick data, historical Support/Resistance, RSI, MACD.
- **Action**: It analyzes the multitime-frame trend. Are we near a breakout? Is the stock overbought on the 1m but just starting a trend on the 15m?
- **Output Example**: *"Bullish. Price structure shows a clear cup and handle breakout above ₹2800 resistance on the 5m chart. RSI is 62 (Healthy)."*

### Agent 2: The Order Book / Microstructure Analyst
- **Role**: Reads the tape and sniffs out institutional money.
- **Inputs**: Level 2 Market Depth (Top 5 Bids / Asks).
- **Action**: Calculates the order imbalance. Are there massive buy limit orders stacked below the current price acting as a floor? Are large block trades hitting the ask?
- **Output Example**: *"High Buy Imbalance. 65% of level 2 depth is heavily stacked on the bid. Institutional accumulation detected."*

### Agent 3: The Catalyst & Sentiment Analyst
- **Role**: Ensures there isn't a fundamental trap.
- **Inputs**: Web scraper for live news headlines, BSE corporate announcements, sector performance.
- **Action**: Is there news driving this breakout? Or is it a random spike?
- **Output Example**: *"Positive sentiment. Reliance just announced a new green energy initiative 15 minutes ago. Sector is up 1.2%."*

### Agent 4: The Risk Manager
- **Role**: Protects the capital.
- **Inputs**: User's account capital, max allowed loss per trade (e.g., 1%), The TA Agent's identified support level.
- **Action**: Calculates the precise Stop Loss (SL), Take Profit (TP), and Position Size. If the SL is too far and throws off the Risk:Reward ratio (> 1:2), it vetoes the trade.
- **Output Example**: *"Trade Approved. Capital: ₹1,00,000. Risk 1% (₹1000). Entry: ₹2810. SL: ₹2790 (₹20 risk). Qty to Buy: 50 shares. TP: ₹2850."*

### The Meta-Agent (The Chief Investment Officer)
- **Role**: The ultimate decision-maker.
- **Inputs**: The reports from Agents 1, 2, 3, and 4.
- **Action**: Synthesizes the information. It checks for **Confluence** (do all agents agree?). If the TA Analyst says "Buy" but the Order Book Analyst sees a massive sell wall, the Meta-Agent passes on the trade. 
- **Execution**: If all conditions align, the Meta-Agent generates the final JSON payload and fires the order execution API (DhanHQ).

---

## Execution Flow (The User Experience)

1. **Background**: System calculates `CURRENT_BEST = "TATA MOTORS"` at 10:14 AM.
2. **User**: Clicks **"Start Trading"** at 10:14:12 AM.
3. **Backend**: Pulls `"TATA MOTORS"`. Spins up the 4 Agents in parallel.
4. **Analysis**: Agents fetch live candles, order book, and news. (Takes ~3-5 seconds).
5. **Meta-Agent**: Synthesizes data. Resolves exact Entry, Stop Loss, and Target parameters.
6. **Execution**: Strikes the API, executes the trade.
7. **UI Update**: Pushes a beautifully styled summary to the user's dashboard:
   > *"Initiated LONG on TATA MOTORS at ₹980. Confluence achieved across Technical (+2% Sector Trend), Order Book (Buy Imbalance), and Catalyst (Auto Sales Data). SL placed at ₹972."*
