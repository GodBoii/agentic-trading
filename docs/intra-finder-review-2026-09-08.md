# Intra-Finder review, September 8, 2026

Reviewed all six supplied tasks, including the older architecture discussion, current local code at `bfd46e0`, local August 31 and September 1 event archives, and Ubuntu September 2–8 reports and event archives. Read September 7–8 one-second price records for stocks with events. Ubuntu also reports checkout `bfd46e0`. This was a read-only production review. No configuration, service, order or application code was changed.

## Assessment

Keep the broad universe, bounded feed reception, optimized ranker and independent AI decisions. The next work should establish which stocks deserve attention, fix broken observation continuity, and remove remaining processing stalls. Another architecture replacement is unnecessary.

Earlier recommendations to impose detector direction, supply detector explanations to the agent, limit tool calls, or shorten model reasoning conflict with the user's later choices. They are not recommendations from this review. AI inference timing remains outside this optimization scope.

## Fresh measurements

Daily event counts come from JSONL records filtered to their own market date, not process status counters.

| Date | Events | Unique stocks | VWAP reversion events |
| --- | ---: | ---: | ---: |
| August 31, local | 505 | 98 | 246 |
| September 1, local | 225 | 81 | 97 |
| September 2, Ubuntu | 650 | 111 | 309 |
| September 3, Ubuntu | 842 | 126 | 417 |
| September 4, Ubuntu, partial | 37 | 23 | 25 |
| September 7, Ubuntu | 848 | 118 | 459 |
| September 8, Ubuntu | 750 | 123 | 420 |

On September 8, Andhra Paper produced 35 alerts. Repetition is established; whether each repeated alert identifies a new useful opportunity is unproven.

For a descriptive forward-price check, read 770,123 one-second rows on September 7 and 1,066,771 on September 8 for event stocks. Match by exchange and security ID, sort and deduplicate timestamps, and take the first observation at or after event creation plus five minutes, requiring it to arrive within ten seconds of that horizon. Use the saved event price as the reference. Subsequent range uses observed prices after event creation through that endpoint.

| Date | Events with endpoint | Median subsequent range | Positive detector-direction return | Mean detector-direction return |
| --- | ---: | ---: | ---: | ---: |
| September 7 | 760 of 848 | 0.9003% | 47.76% | +0.0169% |
| September 8 | 704 of 750 | 0.9240% | 45.03% | -0.0735% |

These are descriptive price outcomes, not executable profits or strategy win rates. They exclude fees, spread, slippage, AI decisions and actual entry timing. Missing endpoints are excluded and may bias results. Repeated stock events overlap, and two days are not independent validation. A future high-low range is not a claim that a trader could capture that range. No matched non-event control was evaluated in this review, so improvement over a simpler sorter remains unproven.

The current selector finds moving stocks. These observations do not establish that its direction predicts returns, or that its setup gates improve attention selection. Evaluate discovery separately from the AI's trading decisions.

## Confirmed remaining problems

1. Setup continuity. `stages/intra_finder.py` evaluates setups only for hot stocks ranked at most 10. `stages/setups/base.py` retains armed time without a last-evaluation gap check. Menon Pistons armed at 10:19:56 and triggered at 11:23:57 on September 8 for a five-second hold rule. Thirty-five events that day had armed-to-trigger intervals above 30 seconds. Elapsed time does not prove continuously observed qualification. Expire interrupted observations and reset on reconnect or invalidation. Test with rank exits and reentries, sparse packets and restarts.

2. Opening-range validity. `LiveStockState._update_opening_range` marks a range complete after 09:30 whenever a prior range high exists. It does not prove opening-window coverage. The final September 8 process requested 567 recoveries and completed zero. Track coverage and provenance, repair recoverable gaps, and distinguish incomplete data from a valid opening range.

3. Historical profile recovery. The morning report has 2,151 ready profiles, 122 partial profiles and 1,237 failed profiles across 3,510 stocks. It separately has 3,495 ready intraday baselines, so daily-profile failures do not mean volume baselines are equally incomplete. `_daily_frame` accepts cache freshness based on today's file modification date and returns unavailable on a failed refresh instead of falling back to an older validated profile. Venue selection can favor the remaining successful venue when the prior venue's history fails. Preserve dated last-known-good profiles, retry a bounded failed subset, and avoid switching venues on incomplete evidence. Keep genuinely unknown profiles explicit because zero ATR changes detector thresholds.

4. Tail latency remains. The final process connected at 14:53:07 and ended at 15:30. Its packet-weighted histogram contains 2,116,746 observations. About 16.69% waited over 250 ms. The p95 bucket is 500–1,000 ms; the p99 bucket is 2,500–5,000 ms; maximum is 4,739.54 ms. These are local ingress-to-processing delays, not exchange-to-agent latency. Ranking peaked at 1,736 ms, checkpoint construction at 1,163 ms and status construction at 1,205 ms. Their maximum timestamps do not establish a common cause. Profile per-packet snapshot/recording cost and concurrent serialization alongside ranking before choosing the next optimization. Earlier morning maximum 9,792 ms belongs to the earlier process and must not be erased by reporting only the post-restart run.

5. Session reporting. September 8's final status says 12 events, while the durable day archive contains 750. September 3 status says 1,492 while the day-filtered archive contains 842. Some final snapshots contain zero activity despite durable events. Persist session and process identities, derive daily totals from durable records and record deployment/configuration intervals. A healthy container or zero reconnects after a restart does not prove an uninterrupted day.

6. Selection and replay evidence. Defaults track roughly 60 hot stocks but evaluate setups only in the top 10. That cutoff has not been validated for opportunity capture. Raw capture is `hot_only`; the current opportunity replay consumes raw packets, so it cannot faithfully rerank the whole market from these tapes. Broad one-second records are available for coarse controls and missed-move research, but cannot reproduce every intrasecond sequence or exact live feed timing. Use those records honestly, and reserve targeted full-packet capture for continuity validation.

## Recommended sequence

First fix setup continuity, opening coverage, profile fallback and day-level reporting. These are correctness changes, not strategy tuning.

Then build a daily comparison of the existing top-10 setup path, top-30/top-60 observation, and a simple recent-volume/price-movement sorter. Record capture before a move, time spent moving, spread, turnover, repeated alerts and missed stocks. Include a short-window participation measure so an unusually busy morning cannot dominate solely through cumulative volume for the rest of the day. Test this as a hypothesis, not an assumed improvement.

Use observed episode resets for repeat suppression and compare the result with current behavior. Do not impose an arbitrary long cooldown or additional hand-tuned quality score without evidence.

Separate sessions by code/configuration and data coverage, freeze candidate rules, then evaluate on untouched days. Historical July/August quality-v3 failures concern an older detector and must not be presented as tests of the current version. Likewise, September shadow data cannot qualify live agent behavior, NIFTY monitoring or chart-worker performance when those paths are disabled.

Continue measured latency work against full-session packet histograms and combined feed/chart load. Prefer smaller captured payloads and bounded work over more workers on the shared two-core server. Keep the agent's independent BUY/SELL/no-trade decision and unrestricted tool workflow intact.
