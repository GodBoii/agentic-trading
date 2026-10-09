# Weighted specialist forecasts

This offline experiment asks whether combining separate data-based predictors
beats individual predictors and one joint regression. It compares seven frozen
variants using the same account engine, fees, data cohort and forecast rows.

- Momentum specialist using 15-second and 60-second returns.
- VWAP deviation specialist.
- Five-level depth imbalance specialist.
- Spread specialist, primarily a cost predictor.
- One joint ridge using all five inputs.
- Equal arithmetic average of the four specialist forecasts.
- Convex weighted average trained on a separate chronological development day.

Every specialist estimates both long and short executable net returns. A VWAP
specialist can learn continuation or reversion from its fitted coefficient; its
name does not assert which theory the local data supports. The spread specialist
adds execution-cost information rather than a separate directional theory.

Read [the preregistration](preregistration.md), [sources and formulas](sources.md),
and [findings](findings.md). Original track 08 already combined features through
regression coefficients and used a logistic probability gate. This experiment
adds an explicit comparison of independent forecasts and learned blend weights.

Base predictors and all feature normalization train on August 19-20, 2026.
Weights train on August 21 predictions from those frozen base models. Evaluation
uses August 24-25, August 31 and September 1. Previously inspected historical
sessions are diagnostic data, not a pristine holdout. `recent_trade` enforces the
existing known-freshness requirements; `receipt_proxy` permits unknown freshness
and is a sensitivity case. Neither verifies original source quote age.

Run from the repository root with `python -m research.42_weighted_ensemble.run`.
Existing versioned evidence cannot be overwritten. Checks run with
`python -m pytest research/42_weighted_ensemble/tests -q`.

`models/initial-v1/frozen-models.json` records fitted values and training hashes
before evaluations. `runs/initial-v1` records the shared source snapshot,
account replays, trades and forecast diagnostics. `preferred_side_accuracy`
means choosing the side with the higher realized executable net-return label.
Both sides can lose. It is separate from profit frequency and account returns.
Fixed-label and account exits can differ because the account also has target,
stop and risk rules. No broker connection or live orders are involved.
