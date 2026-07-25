This paper is by Carlo Zarattini and Andrew Aziz, published in November 2023. It's about a trading indicator called VWAP and whether it can be turned into a profitable day trading strategy. Here's the whole thing broken down simply.

**What is VWAP?**

VWAP stands for Volume Weighted Average Price. It's basically the "true" average price a stock has traded at during the day, but weighted by how much volume traded at each price. If a huge number of shares traded at $100 and only a few traded at $101, VWAP will sit very close to $100, because that's where most of the actual buying and selling happened. This is different from a simple moving average, which just averages price and ignores volume.

Big institutional investors watch VWAP closely because it's used as a benchmark: if a fund buys a stock below the day's VWAP, they got a "good" price; if they buy above it, they got a "worse" price relative to everyone else trading that day.

**The core question of the paper**

The authors wanted to know: if a stock is trading above its VWAP, does that tend to mean it will keep going up? And if it's below VWAP, does it tend to keep going down? In other words, is VWAP a real signal of momentum/trend, or is it meaningless?

To test this, they took every 1-minute candle of the Nasdaq-100 ETF (QQQ) from 2018 to 2023 and split them into two buckets: minutes where the previous candle closed above VWAP, and minutes where it closed below VWAP. They then added up all the price changes in each bucket. The result: when QQQ was trading above VWAP, it tended to keep drifting up (about +$320 total over the whole period); when below VWAP, it tended to keep drifting down (about -$280). So yes — price location relative to VWAP did seem to carry real, persistent information about the direction of the next move.

**The trading strategy they built**

Based on that finding, they created a very mechanical day-trading system:

- Wait for the first 1-minute candle after the 9:30am market open to close.
- If price is above VWAP at that point, go long (buy).
- If price is below VWAP, go short (sell).
- Stop loss: exit the moment a 1-minute candle *closes* on the other side of VWAP (not just touches it — it has to close there).
- If never stopped out, close the position automatically at 4pm.
- No overnight positions — everything is flat by the close.
- They use 100% of the account's money on every trade (no leverage, no fixed % risk per trade), because the stop distance isn't predictable in advance.
- They assumed a small, realistic commission ($0.0005 per share, similar to Interactive Brokers).

Because price can whip back and forth across VWAP many times in a day, this strategy can trigger many trades in a single session — sometimes get stopped out repeatedly with small losses, then finally catch a real trend and hold it to the close.

**How well did it work? (QQQ)**

Starting with $25,000 on January 2, 2018 and running to September 28, 2023:
- The VWAP strategy grew it to $192,656 — a 671% total return (about 43%/year).
- Just buying and holding QQQ over the same period would have grown it to about $56,500 — a 126% return (about 15%/year).

The active strategy also had much less pain along the way: its worst drawdown (peak-to-trough loss) was only 9.4%, versus 35.6% for buy-and-hold. Its Sharpe ratio (return per unit of risk) was 2.1, three times better than buy-and-hold's 0.7. Statistically, the strategy's excess return ("alpha") was 38% per year and highly significant, and it had essentially no correlation with the overall market — meaning it made money somewhat independently of whether the market itself went up or down. That's valuable because it did well through both the 2020 COVID crash and the 2022 bear market.

**Turning up the leverage: TQQQ**

TQQQ is a leveraged ETF that aims to deliver 3x the daily return of QQQ. The authors ran the exact same VWAP strategy on TQQQ instead. Results were dramatic: $25,000 grew to $2,085,417 — an 8,242% total return (116%/year average). Volatility went up substantially (54% vs 18% for the QQQ version), and the maximum drawdown rose to 36.1% — but that's actually about the same drawdown as just passively holding plain QQQ (35.6%), while offering vastly higher returns. Their point: if you're already comfortable with the drawdown of buy-and-hold QQQ, this leveraged active strategy offered similar pain but much bigger gains.

**The nuts and bolts: trades, commissions, win rate**

This is a high-frequency-ish strategy — about 22,000 trades over the ~5.7 years for each version. Commissions were tiny for QQQ ($6,547 total) but became meaningful for TQQQ ($400,619) simply because far more shares had to be traded to deploy the same dollar amount (TQQQ is priced lower and moves more, so more shares change hands).

Interestingly, the win rate (hit ratio) was only about 17% — meaning roughly 5 out of 6 trades lost money. But the strategy still worked because winners were about 5.5x bigger than losers on average. This is a classic "trend-following" profile: lots of small losses while waiting for the occasional big trending day, and those big days more than make up for all the small stop-outs.

**Is VWAP special, or would any moving average work?**

To check whether VWAP itself mattered (versus just "any trend-following signal would have worked"), they reran the same strategy but replaced VWAP with simple moving averages (SMA) of 9, 20, 100, and 200 periods. None of them came close to VWAP's performance:

| Signal | Total Return | Max Drawdown |
|---|---|---|
| VWAP | 671% | 9% |
| SMA9 | 202% | 41% |
| SMA20 | 49% | 42% |
| SMA100 | 83% | 17% |
| SMA200 | 135% | 21% |
| Buy & Hold | 126% | 36% |

Short moving averages traded way too often (100,000+ trades) and racked up more false signals and commissions. Longer moving averages reacted too slowly to reversals, giving back a lot of profit before exiting. VWAP, because it incorporates volume, seemed to strike a better balance — reacting quickly to real shifts in buying/selling pressure (backed by volume) rather than just price noise.

**Does time of day matter?**

They also checked when during the trading day the strategy actually made its money. Most of the profit came from the first couple hours after the open (9:30am–12pm) and the last hour before the close (3pm–4pm). The middle of the day (roughly 12pm–3pm) contributed little to nothing — prices tend to chop sideways with no clear trend then. Their theory: early in the day, momentum traders pile in and reinforce the move; late in the day, institutions rushing to finish executing large orders before the close add pressure that reinforces whatever trend already exists. This suggests a more efficient version of the strategy might skip trading during the flat midday lull.

**Caveats the authors themselves flagged**

- This is a backtest, not a live track record — past performance doesn't guarantee future results.
- They explicitly say they don't consider this "a fully developed trading system," just evidence that VWAP has real signal value.
- The no-slippage assumption gets shakier as account size grows; they say the system isn't meant for managing very large funds in U.S. equities due to liquidity limits.
- A 17% win rate is psychologically hard for many traders to stick with in real life, even if it's profitable on paper.
- Higher commission rates than what they assumed (professional/institutional rates) could meaningfully hurt returns, especially on the high-frequency TQQQ version.

**Bottom line**

The paper argues that price relative to VWAP isn't just a backward-looking benchmark used by institutions to judge execution quality — it also has forward-looking value as a trend signal. A simple mechanical "long above VWAP, short below VWAP" system beat buy-and-hold by a wide margin on both risk and return, beat comparable moving-average-based systems, and scaled up impressively (with proportionally higher risk) when applied to a leveraged ETF. The authors frame it as a promising research finding and a starting point for more rigorous strategy development, not a plug-and-play guaranteed-profit system.
