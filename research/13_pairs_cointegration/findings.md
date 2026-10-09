# Fixed-pair findings, 2026-10-01

The fixed ICICI/AXIS pair fails the tested data and hedge assumptions. No pair trades were simulated, no formal cointegration test was run, and this diagnostic is not an account-replay result.

Strict mode admits 19 development paired minute points, below the 100-point minimum. It therefore fits no model. Receipt-proxy mode admits 705 points from Aug20 and Aug21. ICICI observations are absent on Aug19. The development fit is:

`log(ICICI) = 11.0027684 - 0.5259392 * log(AXIS) + residual`

Residual standard deviation is 0.0026962 in log-price units. The negative beta means this development fit does not support the intended opposite-direction long/short hedge. The counterfactual refuses nonpositive beta rather than taking its absolute value or searching another pair after seeing the outcome.

The development residual's descriptive minute AR1 coefficient is 0.986192. Under stable stationary AR1 assumptions, this implies approximately 49.85 minutes of half-life. That is much longer than the proposed five-minute holding diagnostic, and those stability assumptions have not been established. Two sessions of dependent minute observations are not enough to infer a persistent equilibrium between two banks.

| Later session | Eligible proxy paired points | Reason or result |
|---|---:|---|
| Aug24 | 0 | Neither fixed-pair instrument appears in the cached cohort tape. |
| Aug25 | 0 | Neither fixed-pair instrument appears in the cached cohort tape. |
| Aug31 | 315 | Mean frozen z-score 6.8468; every admitted point exceeds magnitude two. Descriptive AR1 phi is 1.001445, so no stationary half-life is reported. |
| Sep1 | 0 | AXIS is absent; ICICI has 13,035 retained observations. |

Aug31 has 275 regular one-minute residual lag pairs after dropping gaps. Only 46.55% move closer to the frozen training mean. This is drift away from the small development sample, not evidence of executable convergence. Missing quotes and a negative hedge coefficient make the default counterfactual produce zero scenarios in all eight date/mode evaluations.

## Verification and limitations

Six tests pass. They cover as-of prefix causality, strict versus proxy admission, known-coefficient OLS with deliberately noisy residuals, exclusion of gap transitions from AR1, exact two-leg fee accounting on synthetic flat prices, non-overlapping scenarios, and insufficient training refusal. Some tests combine these behaviors. Python compilation passed.

Final evidence is `runs/initial-v3`, with `experiment_kind` set to `pair_diagnostic`. It records 14 date/mode coverage diagnostics, two development model admission/fits, and eight later date/mode diagnostics. None count as common account replays or executable trades. Earlier runs remain superseded evidence with a provenance note; parameters were not retuned.

The environment lacks statsmodels, so no Engle-Granger statistic or p-value appears. AR1 summaries are descriptive. They neither establish I(1) prices nor stationary residuals. Asynchronous last-received prices, limited development sessions, incomplete instrument coverage, source quote age, corporate actions, and regime changes all remain material. The optional two-leg scenario lacks actual simultaneous order control, shortability checks, margin, partial fills, failed-hedge handling, and calibrated impact.

## Next test

Capture both instruments continuously under a fixed cohort with verified quote event times. Fit on a substantially longer preregistered formation period, check integration assumptions using the official econometric implementation, and freeze the hedge before opening new evaluation dates. Do not select another pair because it looks profitable on this same four-session diagnostic. A viable positive hedge and stable residual process would justify implementing a genuine two-leg risk/order controller; the present evidence does not.
