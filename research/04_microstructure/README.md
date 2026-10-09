# Snapshot microstructure research

This folder tests three distinct causal hypotheses on the recorded cohort. None is exchange HFT.

1. Five-level imbalance remains above 0.4 in one direction for 30 seconds.
2. Thirty-second bid-depth growth minus ask-depth growth exceeds 25% of starting total depth and agrees with current imbalance.
3. A quote weighted by five-level totals differs from midpoint by at least 0.4 bps and agrees with at least 1 bps of recent midpoint movement.

The imbalance is `(B5 - A5) / (B5 + A5)`. The weighted quote is `(ask * B5 + bid * A5) / (B5 + A5)`. Depth change is `((B5_t - B5_0) - (A5_t - A5_0)) / (B5_0 + A5_0)`.

One evaluation per instrument per minute limits repeated reactions to the same observation pattern. Unusable quotes and gaps over 15 seconds reset history. Strict freshness and unverified receipt-proxy sensitivities stay separate. Parameters are fixed hypotheses, not estimated profitable thresholds. The shared engine supplies later-observation fills, fees, account limits, cooldowns, and exits.

The original tape retains one received observation per second, not every book event. Aggregate depth can change because levels move in or out of the top five. We cannot infer queue position, cancellation flow, aggressor trades, top-level capacity, or event OFI. A statistically related feature still needs returns large enough to cover spread, fees, and delayed execution.

Run tests from the repo root with `python -m unittest discover -s research/04_microstructure/tests -v`. Research sources are in [sources.md](C:/Users/prajw/Downloads/Trader/research/04_microstructure/sources.md). Results and interpretation are in [findings.md](C:/Users/prajw/Downloads/Trader/research/04_microstructure/findings.md).
