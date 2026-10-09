# Relative volume with a private recorded-data adapter

This experiment tests completed-minute volume surprise, alongside continuation and confirmed reversal signals. The common Tick contract and shared replay engine are unchanged.

The private reader selects original `day_volume` rows for the fixed Aug18 top-twelve cohort. It matches both security ID and exact UTC microsecond receipt timestamp to retained shared ticks, removes ambiguous duplicate identities, and refuses missing or invalid volume. It fingerprints the normalized private volume input and records source paths and the shared quote-cache digest. A receipt timestamp establishes availability to the recorder; it does not prove the source volume-event time.

For each instrument, compute incremental minute volume from the previous minute's last cumulative observation to the current minute's last observation. Admit a completed minute only with at least 40 observations, a start anchor within two seconds of the boundary, an end observation at second 58 or later, and a next-minute observation by second 2. This next observation is the bar's availability time. Gaps above 15 seconds, unusable quotes, missing volume, and cumulative decreases invalidate the minute. The first minute lacks a known anchor, and the final minute lacks its completion event; both stay unavailable.

For each instrument and IST minute of day, fit the mean admitted incremental volume using only Aug19, Aug20, and Aug21. Require all three development days and positive expected volume. Freeze the lookup before evaluating Aug24, Aug25, Aug31, and Sep1. Evaluation samples never update the baseline.

The two fixed hypotheses are:

- Continuation requires completed-minute volume at least twice its baseline and absolute minute midpoint movement at least 5 bps.
- Reversal requires the previous minute's volume at least three times its baseline, previous movement at least 10 bps, and the next completed minute's opposite-direction movement at least 3 bps.

Signals use the shared spread/freshness gates and account engine. Strict and receipt-proxy baselines are fitted independently. Each signal needs a later executable quote; the shared engine supplies fees, delayed orders, exposure reservations, loss limits, and exits. Missing three-day seasonal cells fail closed.

This received-snapshot method cannot identify every trade, recover intra-second sequence, prove venue volume freshness, or establish aggressor direction. Three days leave strong baseline sampling uncertainty and incomplete coverage. This research is not evidence of institutional order flow or a validated live edge.

Run `python -m unittest discover -s research/16_relative_volume/tests -v` and `python -m research.16_relative_volume.run` from the repo root. Existing preparation and run versions refuse overwriting. Source snapshots, baselines, private-input fingerprints, bar-admission counts, account summaries, and trades stay in the owned folder.
