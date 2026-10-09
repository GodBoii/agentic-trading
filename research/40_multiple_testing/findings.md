# Cross-track statistical diagnostic findings

The first clean audit covers 70 distinct variant/freshness validation comparisons across completed initial account-replay versions. Repeatability runs are excluded from the hypothesis family because they repeat the same observations and methods. Invalid/interrupted versions are excluded. Pair, packet, and paired-exit diagnostics are not full-account return series and are not mixed into this audit.

Every included comparison has both recorded validation dates and no unresolved validation positions. This does not imply all development dates are complete. Incomplete August19 exposure remains visible in the relevant mean-reversion and wick findings.

No adjusted diagnostic falls below 0.05. There are only two validation sessions, so the one-sided exact sign-permutation tail cannot be smaller than 0.25 for two positive nonzero outcomes. Testing more variants does not add independent sessions.

The exact sign-flip diagnostic assumes independent symmetric session errors. Benjamini-Hochberg adjustment assumes valid pvalues and appropriate dependence. The recordings do not establish these assumptions. Therefore neither the raw nor adjusted numbers certify statistical significance, profitability, or absence of overfitting.

The positive three-trade same-time-of-day result is concentrated in SBI shorts and has a later audit loss. The two-trade strict peer-reversal profit is similarly too sparse. Neither becomes a discovery by comparing it with many losing methods.

Use [initial-v2 diagnostics](C:/Users/prajw/Downloads/Trader/research/40_multiple_testing/runs/initial-v2/diagnostics.json) for this 70-comparison snapshot. The earlier initial-v1 included duplicate repeatability identities in its list; it is preserved but superseded for this audit. Later research batches need new versioned audits and must keep the full experiment count.

The expanded batch adds the relative-volume and regime-mixture hypotheses. [Initial-v3](C:/Users/prajw/Downloads/Trader/research/40_multiple_testing/runs/initial-v3/diagnostics.json) now contains 78 validation comparisons, all with complete validation exposure. None has an adjusted diagnostic below 0.05. Packet, pair, and volatility-forecast metrics remain separate from account-return testing.

[Methods and source assumptions](C:/Users/prajw/Downloads/Trader/research/40_multiple_testing/README.md).
