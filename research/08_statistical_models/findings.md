# Initial findings, 2026-10-01

The fitted models did not find enough predicted net movement to trade. All 24 policy/session evaluations completed with zero orders and zero P&L. That is a rejection of the tested entry hypotheses on this tape, not a profitable strategy.

Strict admission produced only six development labels, below the preregistered 100-row minimum. No strict model was fitted. Receipt-proxy admission produced 11,283 development labels across Aug19, Aug20, and Aug21. The frozen model then evaluated Aug24, Aug25, Aug31, and Sep1 without retraining or threshold changes.

Development fixed-horizon long labels average -12.28 bps and short labels average -12.19 bps after spread, 1 bps slippage each leg, and frozen fees at approximately Rs100,000 notional. Only 1.69% of long and 1.75% of short development labels were positive. This cost burden dominates typical one-minute moves in the admitted recordings.

| Evaluation session | Proxy labels | Long prediction correlation | Short prediction correlation | Long RMSE bps | Short RMSE bps |
|---|---:|---:|---:|---:|---:|
| Aug24 | 2,887 | 0.177 | 0.185 | 5.16 | 5.20 |
| Aug25 | 2,980 | 0.085 | 0.072 | 6.24 | 6.29 |
| Aug31 | 3,178 | 0.134 | 0.100 | 6.55 | 6.48 |
| Sep1 | 3,203 | 0.083 | 0.105 | 8.45 | 8.42 |

There is weak linear ranking information in some sessions. Most RMSE changes versus the frozen training-mean baseline are small. Logistic Brier scores also move only slightly versus frozen training prevalence, with some cases worse. A correlation above zero does not imply a trade large enough to exceed execution costs. The 2 bps net-return gate, 5 bps gate, and 65% probability gate produced no orders.

Valid evidence is `runs/initial-v2`. It preserves exact coefficients, feature standardization, training/input hashes, model checksum, labels' cost assumptions, forecast diagnostics, trade/account summaries, and source snapshots. `initial-v1` was interrupted because a diagnostic implementation changed during its process and is explicitly invalid. Keep it for provenance and exclude it from conclusions.

Six focused tests passed, including future-prefix causality, refusal to fill at a favorable signal-only quote, invalid future interval rejection, deterministic fitting, immutable coefficient arrays, insufficient data refusal, and no-model signal refusal. Tests share a few cases, so this list describes coverage rather than a count of distinct tests.

## Next experiment

Use verified source quote timing and a fresh date split. Collect more independent market sessions before increasing capacity. Freeze the same linear models as controls, test longer executable horizons with costs tied to the risk-sized order rather than a fixed notional, and compare path-aware labels with the engine's stop/target exits. Move to per-level neural models only after obtaining their actual input tensors and establishing economic improvements over these controls. The author's DeepLOB and multi-horizon repositories are researched references, not models executed in this run.
