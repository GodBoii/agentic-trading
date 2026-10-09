# Fixed bank pair and residual dynamics

The pair is fixed in advance: ICICI Bank, security 4963, and Axis Bank, security 5900. Both belong to the Aug18 prior-date cohort. No search chooses a pair with favorable later returns.

At each UTC minute boundary, sample the latest received quote for each instrument without looking forward. Both quotes must have arrived within five seconds, pass the selected freshness mode, and have spread no larger than 5 bps. Source quote age remains unknown under receipt-proxy mode. Prices can differ in receipt time by up to five seconds, which can create apparent residual movement.

Fit `log(ICICI) = intercept + beta * log(AXIS) + residual` using only Aug19, Aug20, and Aug21. Freeze beta, intercept, and development residual standard deviation. Fewer than 100 usable paired points produces no model. Evaluate Aug24, Aug25, Aug31, and Sep1 without changing the frozen model.

The AR1 diagnostic regresses next residual on a constant and previous residual using only exactly adjacent minute points. It drops gaps and overnight transitions. When `0 < phi < 1`, the conditional approximate half-life in minutes is `-log(2) / log(phi)`. A stationary AR1 and stable parameters are assumptions for this interpretation. We do not test those assumptions or claim cointegration significance. statsmodels was unavailable and no dependency was installed.

The optional two-leg counterfactual requires positive beta and a frozen residual z-score magnitude at least two. It waits one minute, then holds five minutes. Entry and exit quotes must arrive after the previous decision; the entire minute grid must remain contiguous. Gross entry notional is Rs100,000 split in log-regression dollar weights `1 : beta`, rounded down to integer shares. Both orders must fit 1% of displayed five-level depth. Both sides pay spread, 1 bps hypothetical slippage each execution, and exact frozen per-order fees. Scenarios do not overlap within a session.

This is a coarse outcome diagnostic. It does not reserve account cash, guarantee simultaneous fills, model failed hedges or partial orders, simulate impact, establish shortability, or manage leg-risk. Missing minute quotes reject an outcome rather than fabricate a closing trade. Between-minute freshness and path behavior are unknown.

Run `python -m unittest discover -s research/13_pairs_cointegration/tests -v` and `python -m research.13_pairs_cointegration.run` from the repo root. Existing run evidence cannot be overwritten. Initial-v3 is the final run; initial-v1 and initial-v2 are superseded with a provenance note. Source snapshots, input hashes, coverage, frozen model, diagnostics, and any counterfactual outcomes stay under each run.
