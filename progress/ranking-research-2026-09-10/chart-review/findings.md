# September 9 chart and signal review

All 118 stocks were visually inspected using ten contact sheets. `stock-coverage.csv` records panel location, counts and a written observation for every stock. `signal-audit.csv` contains all 660 signals with saved contemporaneous activity metrics and causal bar features. These files are separate from production.

The user's observation is true for several conspicuous trades. AGI Infra, Excelsoft, Orient Green Power, Pashupati, Menon Pistons, Innovision and TCC received AI attention after large earlier moves or near a range. But the blanket claim that the AI chose the least moving stocks is not supported. Bal Pharma's entry preceded a strong ascent. Raymond and Raymond Lifestyle had AI analysis before further declines but no order. Graphite had substantial movement after entry in the opposite direction to the trade.

Using first later minute open as an entry proxy, the median absolute 15-minute close displacement was 0.878% for 35 AI-run signals versus 0.576% for 624 skipped signals with usable future data. Maximum excursion in either direction was 1.633% versus 0.996%. For the 26 broker-submitted entries, the originating signal's median absolute displacement was 0.855%. These are opportunity measures, not trading P&L, and not evaluations at actual execution time.

Timing matters. Fourteen of 35 AI analyses started from signals before 09:30, seven more in 09:30-10:00. None were from signals after 13:30. Across half-hour comparison groups, selected signals had a median forward-move percentile of 58.9%, versus 50.4% for skipped signals. The 09:30-10:00 cohort is a clear weak spot: selected signals' median displacement was 0.352%, skipped signals' 0.688%. There are only seven selected cases in that group, and later groups contain one to three. This is descriptive evidence, not a causal test of the scheduler.

The strongest explanation for missing later opportunities is recorded admission state. There were 417 full-trade-slot skips, 114 analysis-capacity skips and 64 authorization/IP skips. Ranking cannot alone overcome these states. Do not infer that every blocked signal should have become a trade or increase risk limits to force admission.

Examples worth replaying:

| Stock and signal time IST | Rank | Why skipped | Absolute 15m displacement | Detector-direction return |
| --- | ---: | --- | ---: | ---: |
| Responsive Industries 14:03:14 | 10 | Full trade slots | 6.42% | -6.42% |
| Texmo Pipes 11:13:15 | 1 | Full trade slots | 3.84% | +3.84% |
| Texmo Pipes 11:14:54 | 2 | Full trade slots | 4.14% | -4.14% |
| India Nippon 14:59:50 | 2 | Authorization/IP | 5.40% | -5.40% |
| Novartis 09:22:14 | 8 | Analysis capacity | 4.23% | -4.23% |

Texmo's two nearly adjacent signals have opposite detector directions around the same upward opportunity. Several strong later rallies were tagged VWAP_REVERSION SHORT. Preserve independent AI direction assessment and separate opportunity ranking from direction conviction.

Pre-event feature evidence does not support simply rewarding a neat trend or short-term volume acceleration. Within half-hour groups, rank-normalized correlations with absolute forward 15m displacement were +0.291 for prior five-minute range, +0.256 for current hotness, -0.253 for activity rank, +0.080 for recent traded value, -0.017 for bar trend efficiency, -0.047 for three-minute versus preceding twelve-minute volume ratio, and -0.072 for saved activity trend efficiency. Negative rank correlation means better current ranks already relate to greater future movement. This sample contains only top-ranked triggered signals and cannot judge omitted non-signalling stocks.

Selected signals did have lower recent participation. Median saved five-minute traded value was 4.99 million versus 5.57 million for skipped signals, and median causal volume ratio was 0.84 versus 1.12. But only 21 selected signals have sufficient preceding bars for that ratio. Rewarding volume ratio on this one day's outcomes would be unjustified because its forward relation was weakly negative.

Test next across untouched days:

1. Choose the highest current opportunity among simultaneously eligible pending signals, rather than letting whichever event arrives first consume the next slot. Refresh stale candidates and retain existing account risk limits.
2. Compare ongoing recent range, spread-adjusted movement and current turnover against the existing score. Avoid a hard trend-efficiency filter: reversals and new expansions often start with low prior efficiency.
3. Test fresh expansion after contraction as a separate setup, using only closed bars or timestamped ticks. The charts show this pattern in Responsive, Texmo, Jindal Stainless, Share India and Signpost. The shape is a hypothesis; no predictive hit rate is established here.
4. Audit flat traces before treating them as quiet tradeable bases. Several sparse instruments and apparent limit plateaus look attractive in retrospect but may have no executable depth.
5. Measure signal-to-analysis and analysis-to-entry opportunity decay separately. The event-level figures here cannot tell whether the move was still available after AI latency.

Method limits: bar features use completed minutes whose end is at or before the event timestamp. Forward windows start at the next later minute open, excluding the event minute's potentially pre-event high/low. At least 80% minute coverage is required for forward windows. Full-day bars are sampled observations, not exchange-complete candles. Excursions are hindsight upper bounds, not achievable exits. Fixed-window close moves are still direction-agnostic and exclude costs, spread and queue priority. Repeated same-stock signals overlap and are not independent samples. This is one-day hypothesis generation; it must not be presented as out-of-sample strategy validation.
