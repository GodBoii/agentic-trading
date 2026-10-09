# Frozen comparison, version 1

Written before this track opened evaluation outputs on 2026-10-09.
The historical cohort was inspected by earlier tracks. It is not a pristine holdout.

Fit four specialist ridge predictors on 2026-08-19 and 2026-08-20 only.
Use the existing track 08 causal feature definitions and executable net-return
labels, including continuous usable quotes, next-observation entry after 250 ms,
60 second holding period, 1 bp slippage per leg, fees and Rs 100,000 notional.
Specialists use momentum at 15 and 60 seconds, VWAP deviation, five-level depth
imbalance, and spread respectively. Also fit one joint ridge using all inputs.
Every predictor emits separate expected net returns for long and short.

All feature means and standard deviations come from the first two sessions.
Ridge minimizes mean squared error plus 0.01 times squared non-intercept weights.
Constant columns get scale 1. Require 100 base-training rows and 100 rows on the
third development session, 2026-08-21. Otherwise all variants abstain.

Compare the four specialists, joint ridge, equal average and learned convex
average. Equal average uses weights 0.25. Learn one common weight vector across
both side targets using only third-session predictions from frozen base models.
Minimize mean squared error plus 0.1 times squared distance from equal weights,
subject to nonnegative weights that sum to one. Use exact active-set enumeration
over the 15 nonempty faces of the four-dimensional simplex. No hyperparameter
search, validation tuning or model refitting follows weight learning.

Evaluate 2026-08-24, 2026-08-25, 2026-08-31 and 2026-09-01, with separate
recent_trade and receipt_proxy modes. Report per-session and pooled predictive
RMSE, preferred-side accuracy, selected-label profit frequency, error correlation,
and training-constant controls. Preferred-side accuracy means matching whichever
side has the higher realized executable net-return label. It is not the frequency
of profitable trades or an exact raw-price direction metric. Net return labels can
be negative for both sides. Direction ties in target labels are excluded.

Replay all seven variants through the unchanged common account engine. Signal
only if the best predicted net return is at least 2 bps. Target 30 bps, stop 15
bps, horizon 60 seconds and cooldown 180 seconds. Keep account, latency, depth,
fees and risk limits unchanged. Predictive labels omit account constraints and
cannot replace account-return evidence. Replay target/stop exits differ from fixed
60-second label exits and are reported separately.

Save training/input/dependency hashes and models before replaying evaluations.
Save immutable versioned run evidence using the existing common runner. All
historical results remain promotion-ineligible because of prior inspection,
small day count, repeated hypothesis search and unverified source quote age.
