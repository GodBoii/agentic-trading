# Frozen experiment specification

Declared on 2026-10-09 before the first replay. No outcome from these variants was inspected when selecting parameters. This cohort was inspected in earlier work and is not a pristine holdout. No tuning or model fitting occurs in this track.

Compare three rules with identical costs, fills, exits, account limits and seven sessions.

- `kalman_trend` follows a local-linear Kalman slope only when its five-minute projection is at least 15 bps, absolute slope exceeds two model standard deviations, and the observed five-minute move agrees and is between 10 and 100 log-return bps.
- `cusum_continuation` follows the direction of a symmetric CUSUM event with a fixed 15 log-return bps threshold. It detects accumulated changes and does not claim a profit probability.
- `kalman_cusum_agreement` enters only when both standalone direction conditions hold on the same completed minute. This is one predeclared combination. It is not a calibrated probability or learned weight.

The Kalman state is relative log price and slope, in bps and bps/minute. `F=[[1,1],[0,1]]`, `H=[1,0]`, `Q=diag(.25,.04)`, `R=9`, initial mean `[0,0]`, initial covariance `diag(25,4)`. Each instrument uses its first valid completed bar as the log-price anchor. The recursion uses observations available through the current completed minute only. No backward smoother or full-sample expectation maximization runs. The covariance is conditional on an assumed Gaussian model, not an empirical accuracy estimate.

CUSUM computes `S+ = max(0, S+ + r)` and `S- = min(0, S- + r)`. A strict crossing of `S- < -15` or `S+ > 15` emits a signed event and resets only that side, matching mlfinpy's ordering. `r = 10000*log(close_t/close_(t-1))`.

All variants wait for 20 valid consecutive completed minutes. A minute requires at least 10 observations, a first observation by second 10 and a last observation from second 50 onward. Gaps, unusable quotes and incomplete minutes invalidate history. State is independent by instrument. The final partial minute never releases. New entries use the current quote and the shared delayed execution engine, not the historical completed-bar close.

All variants use 30 bps target, 20 bps stop, 600 second maximum holding period and cooldown, and cost-room checks. The shared engine applies the existing fee model, 250 ms latency, 1 bps extra slippage, 10% five-level aggregate displayed-depth cap, entry-drift checks, three-position limit, Rs 100000 position cap and Rs 2500 daily loss stop. Both `recent_trade` and `receipt_proxy` freshness gates run. Unknown age cannot pass the strict gate. The receipt mode is an assumption sensitivity.

Seven cached sessions and 12 prior-universe stocks create 42 account replays. Earlier program phase labels remain descriptive. Primary comparison is all sessions and the four sessions after development. Fewer trades or smaller losses alone does not establish improved accuracy. The no-trade benchmark has zero PnL. Reject a claim of demonstrated live edge if metadata is unverified, any session remains incomplete, or the sample is too small to support inference.
