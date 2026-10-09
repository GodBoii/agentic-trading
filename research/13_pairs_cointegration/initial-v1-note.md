# Initial-v1 provenance

Initial-v1 completed. A synthetic OLS test tolerance was corrected because the deliberate alternating residual has a small linear component. The resulting intercept differs by 0.0000615, so the assertion tolerance changed from four to three decimal places. Model fitting and policy thresholds did not change.

Initial-v2 adds rejection-reason counts to explain missing pair observations. Use initial-v2 for final findings; retain initial-v1 as superseded diagnostic evidence. No parameters were tuned to returns.

Initial-v3 adds an explicit `pair_diagnostic` experiment kind and names the result file `diagnostics.json` so the global account-replay verifier cannot confuse this track with an account backtest. Final findings use initial-v3. Initial-v2 remains superseded evidence. Computations and parameters are unchanged.
