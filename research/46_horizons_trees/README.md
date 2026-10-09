# Horizon and nonlinear forecast comparisons

This experiment compares single momentum rules, train-only ridge and histogram gradient boosted trees over 5, 15 and 30 minute horizons. It uses the shared minute-candle cohort and account engine under `research/45_market_dataset`.

`specification.json` declares the complete finite grid before outcomes from these experiments are inspected. `sources.md` explains formulas and primary documentation. `findings.md` records the completed results and limits.

The grid contains 36 active validation trials and a no-trade comparator in nine selection groups. Three distinct validation control accounts supply the identical no-trade comparator for each family's horizon. Validation chooses one candidate per family and horizon only if it has at least 100 trades and beats zero account PnL. Otherwise that policy freezes abstention. No parameters, thresholds or horizon are selected using test PnL.

One model per learned family and horizon fits 2022-2023 rows. Models and scalers do not refit on 2024. Threshold and momentum-rule selection uses 2024 account outcomes at 2 bps adverse cost per leg. The selection file becomes durable before evaluating 2025-2026 predictions. Both 2 and 5 bps test sensitivities replay those same frozen policies. Each account reserves capital and slots, forbids overlap in an instrument and applies the shared realized-loss halt. This is a daily-reset account simulation with scheduled candle references, not verified exchange fills.

Run from the repository root after the shared cache is complete:

```powershell
python -m unittest research.46_horizons_trees.test_methods -v
python -m research.46_horizons_trees.run
python -m research.46_horizons_trees.verify
```

`run` refuses to overwrite `runs/initial-v1`. Preserve frozen evidence and write a newly declared specification/run name for a later experiment. It limits OpenMP and BLAS thread pools to two while fitting and predicting.

Saved evidence includes source snapshots and SHA256s, the shared manifest, every validation account/trade/daily ledger, nine group controls, saved validation and test forecasts, safe ridge JSON and boosted-tree NPZ state, selected-policy freeze, all test accounts and comparative metrics. `verify` independently evaluates saved model state without an estimator pickle and checks hashes, trade chronology, nonoverlap, capacity and accounting.

All horizons use the same admitted decision cohort. Full-session admission and a current available-stock universe are conditional data filters. Test history is locally available history and is not claimed as a pristine holdout. The peer basket uses synchronous available stocks and is not an index/sector hedge. Feature causality does not resolve missing original timestamp semantics, corporate action provenance, actual depth, margin, short availability or bid/ask spreads.
