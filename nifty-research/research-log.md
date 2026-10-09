# Research log

## 30 September 2026

The initial audit found about 19.19 GB across two local archives. Meaningful recordings cover 16 trading dates. August 20 and 21 have almost complete regular-session coverage. The Ubuntu collector is disabled and its old snapshot is stale.

Observed problems include incomplete June 23 ask-side recording, long July gaps, restart sequences, aggregated volume increments classified using the latest observed price, noisy wall events, and CVD carried across dates. The first implementation recomputes state from validated raw Full packets, pairs depth backward, and keeps unresolved replay exits visible.

Implemented a chronological forecast experiment, explicit option payoff library, conditional bid/ask replay, provenance manifests and regression tests. Initial tests caught a timestamp precision mismatch between microsecond arrays and nanosecond lookup instants; lookup now normalizes precision explicitly.

The first result table will be preserved without picking thresholds or feature subsets based on its profits. Any refinement using these dates is exploratory. Fresh dates will be required for confirmation.

The first completed cycle scores 1,602 forecasts on nine later dates. Nearby depth improves daily MSE on eight dates, but its descriptive interval includes zero and every fitted model loses to a zero-return reference on RMSE. Deeper features worsen the aggregate forecast error. Every conditional option-replay policy is negative after costs. No execution promotion is justified.

Added a known session-close gate after reviewing position lifecycle, so the replay cannot plan an overnight exit. Unresolved intraday exits remain explicit and block later trades that date. Added a historical agent bundle that excludes future labels and P&L. Verified the full cached pipeline and 18 regression tests.
