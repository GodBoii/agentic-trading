This is the definitive, re-evaluated, step-by-step logic to filter 7,000+ stocks down to The Single Best Candidate for intraday trading.

This logic moves away from "Top Gainers" (which chases the past) to "Momentum Ignition" (catching the move as it starts). It is designed to be implemented in Python using the DhanHQ API.

The Architecture: The "Alpha Funnel"

We process the market in three concentric circles.

The Universe (Static): 7,000 
→
→
 250 (Pre-Market)

The Watchlist (Dynamic): 250 
→
→
 5 (Real-Time Screening)

The Champion (Selection): 5 
→
→
 1 (Scoring & Ranking)

Phase 1: Pre-Market Filtration (8:30 AM - 9:00 AM)

Goal: Remove noise, illiquidity, and manipulation risks.

Input: All NSE Equity Symbols (~2,000 active).
Logic:

Liquidity Gate:

Filter: Average Daily Turnover (Last 10 Days) 
>
₹
10
 Crores
>₹10 Crores
.

Reason: Ensures you can enter/exit instantly without slippage.

Volatility Potential:

Filter: Average True Range (ATR %) 
>
1.5
%
>1.5%
.

Reason: Dead stocks don't pay. We need stocks that naturally move.

Price Filter:

Filter: Price 
>
₹
50
>₹50
 AND Price 
<
₹
5
,
000
<₹5,000
.

Reason: Filters out penny stocks (operator driven) and super-heavy stocks (low liquidity).

Circuit Filter:

Filter: Exclude stocks currently in Trade-to-Trade (BE/BZ series) or GSM/ASM frameworks.

Output: A "Tradeable Universe" of roughly 200-250 stocks. Load these into memory/Redis.

Phase 2: Real-Time Monitoring (9:15 AM Onwards)

Goal: Detect the "Ignition" of a move.

Input: Live WebSocket Tick Data for the 250 stocks.
Logic (Run every 1 minute):

Step A: The Regime Check (Market Context)

Before looking at stocks, look at the Index (NIFTY 50) and VIX.

Rule: If NIFTY is 
<
−
0.5
%
<−0.5%
 (Red) AND India VIX is Rising 
→
→
 Short Candidates Only.

Rule: If NIFTY is 
>
+
0.5
%
>+0.5%
 (Green) AND India VIX is Stable 
→
→
 Long Candidates Only.

Rule: If India VIX 
>
24
>24
 
→
→
 HALT TRADING (Too risky/choppy).

Step B: The Ignition Filter (The "Spark")

Apply these filters to the 250 stocks live. A stock must pass ALL to survive.

Relative Volume (RVOL) Check:

Formula: 
Current Cumulative Vol
/
Avg Vol at this specific time
Current Cumulative Vol/Avg Vol at this specific time
.

Threshold: 
1.5
<
RVOL
<
3.5
1.5<RVOL<3.5
.

Reason: High enough to show interest, low enough to avoid exhaustion/climax.

The "Power Move" Check:

Long: Current Price 
>
Intraday VWAP
>Intraday VWAP
 AND Price 
>
Day Open
>Day Open
.

Short: Current Price 
<
Intraday VWAP
<Intraday VWAP
 AND Price 
<
Day Open
<Day Open
.

Reason: Ensures we are on the right side of the institutional average price.

The FOMO Guardrail:

Formula: 
Abs
(
Price
−
VWAP
)
/
VWAP
Abs(Price−VWAP)/VWAP
.

Threshold: Must be 
<
2.5
%
<2.5%
.

Reason: If a stock is already 3% away from VWAP, the move is over. Do not chase.

Sector Confluence:

Logic: Map stock to its Sector Index (e.g., INFY 
→
→
 NIFTY IT).

Threshold: Sector Index must be trending in the same direction (
>
0.25
%
>0.25%
 for Long).

Output: A list of 3 to 8 "Active Candidates".

Phase 3: The Champion Selection (The Scoring Engine)

Goal: Mathematically rank the Active Candidates to pick the ONE best stock.

We apply a weighted score (0-100) to the remaining candidates.

The Formula:

Final Score
=
(
30
×
𝑆
Mom
)
+
(
30
×
𝑆
Tech
)
+
(
20
×
𝑆
Micro
)
+
(
20
×
𝑆
Cat
)
Final Score=(30×S
Mom
	​

)+(30×S
Tech
	​

)+(20×S
Micro
	​

)+(20×S
Cat
	​

)

1. Momentum Score (
𝑆
Mom
S
Mom
	​

):

Calculate Volume Acceleration: Is volume increasing in the last 5 minutes compared to the 5 minutes before that?

Highest acceleration gets max points.

2. Technical Score (
𝑆
Tech
S
Tech
	​

):

Breakout: Is Price breaking the "Opening Range" (High of first 15 mins)? (+Points)

Trend: Is Price above 20 EMA? (+Points)

3. Microstructure Score (
𝑆
Micro
S
Micro
	​

):

Bid-Ask Spread: Tight spread = High Score.

Imbalance: (Buy Orders at Top 5 Depth) vs (Sell Orders at Top 5 Depth). Stronger Buy pressure = High Score (for Long).

4. Catalyst Score (
𝑆
Cat
S
Cat
	​

):

Does the stock have news today (Earnings, Order Win)? (Checked against pre-market scraper).

Yes = 100, No = 0.

Phase 4: The Final Output (The Handoff)

Sort the candidates by Final Score descending.

Select the top stock (Candidate_1).

Validation Check:

Is Final Score 
>
75
>75
?

YES: Output stock name ("XYZ") to Aetheria AI.

NO: Output None. (Better to stay cash than force a weak trade).

Summary of the Logic Flow for Code Implementation

8:30 AM: Run Universe_Filter. Input: 2000 stocks. Output: watchlist.csv (250 stocks).

9:15 AM: Connect DhanHQ_WebSocket for 250 stocks.

Loop (Every 1 min):

Get Market_Regime (Nifty/VIX).

Filter watchlist for RVOL > 1.5, Price > VWAP, Sector Green.

Result: active_list (e.g., [TATASTEEL, INFY, SBIN]).

Scoring:

Calculate Composite_Score for all 3.

TATASTEEL: 82 (High Vol Acc, High Depth).

INFY: 65 (Good Vol, Low Depth).

SBIN: 40 (Choppy).

Result: "TATASTEEL" is the winner.

Action: Pass string "TATASTEEL" to Aetheria_AI_Team.

This logic is robust because it rejects noise (Phase 1), ensures momentum (Phase 2), and uses math to pick the strongest runner (Phase 3), removing all human bias.