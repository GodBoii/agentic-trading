# Initial findings, 2026-10-01

All three snapshot hypotheses lose money in the common execution model. No threshold was changed after seeing these results. The seven-session result does not establish that all order-book models fail; it rejects these specific defaults on this downsampled, freshness-limited cohort.

| Hypothesis | Strict trades | Strict net Rs | Unverified receipt-proxy trades | Proxy gross Rs | Proxy fees Rs | Proxy net Rs |
|---|---:|---:|---:|---:|---:|---:|
| Persistent five-level imbalance | 11 | -1,385.77 | 167 | -5,919.57 | 11,958.11 | -17,877.68 |
| Normalized snapshot depth change | 20 | -2,187.36 | 176 | -6,196.78 | 12,129.68 | -18,326.46 |
| Aggregate weighted quote and trend | 6 | -629.81 | 175 | -6,444.01 | 11,525.78 | -17,969.79 |

Every proxy variant lost in all seven sessions and triggered the common daily loss halt each day. They already lose before explicit fees, with spread and hypothetical slippage included in gross P&L. Brokerage and statutory fees add most of the remaining loss. A displayed imbalance signal alone does not leave enough executable price movement in these recordings for the 60-second holding experiment.

All 42 policy/session runs completed with no unresolved positions. Five behavior tests cover arithmetic, persistence, causal warmup, unknown freshness/gap resets, and instrument isolation. The input manifests, common account settings, exact source snapshot, trade files, rejection counts, and phase-specific aggregates are preserved in `runs/initial-v1`.

The strict sample is small and concentrated in Aug21 and Aug25. Its zero-trade sessions are data-admission failures, not successful capital protection proved in live trading. Receipt-proxy results assume usable received quote snapshots despite unverified source quote timing. None of these outcomes is live or promotion-eligible.

## What changes next

Collect complete per-level books and source event times before trying true OFI, fitted microprice, passive queue models, or neural book tensors. Use the proxy hypotheses as negative controls when evaluating the improved feed. For any new predictive model, measure future executable net returns after decision latency rather than contemporaneous midpoint correlation. Keep these losing runs so a future comparison cannot quietly change the cost model or erase the original failure.

See [sources.md](C:/Users/prajw/Downloads/Trader/research/04_microstructure/sources.md) for the primary papers and author's repository that motivated the experiments. Their markets, feature definitions, and prediction tasks differ from this recording.
