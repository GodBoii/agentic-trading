# SSRN 4631351 review and local tests

This track reviewed the supplied 26-page VWAP paper and tested two predeclared NSE adaptations. It found no profitable edge. The momentum confirmation did not rescue the candle strategy.

The paper's volume weights are inside the VWAP average. They are not learned weights across predictors. Our second variant adds a fixed confirmation filter; the separate ensemble research should answer the learned-weight question.

Read `sources.md` for the original formulas, page references and replication limits, and `findings.md` for measured results. `hypotheses.json` and `candle-hypotheses.json` were written before their evaluations. No thresholds were tuned after seeing the results.

## Experiments

1. The candle experiment uses the first six available minute-data security IDs in numeric order. It recomputes the paper's typical-price session VWAP, trades the prior completed candle's direction at the next candle open, reverses on direction changes and exits at the session close. A second variant also requires five-minute momentum, latest-minute agreement and path efficiency. Each name has an independent INR 100,000 sleeve. Scenarios charge current NSE fees and 0/1/5 bps adverse slippage per side.
2. The quote experiment applies vendor-VWAP direction to completed midpoint bars in the earlier fixed 12-stock,7-day comparison. It retains the shared engine's fixed stop, target and horizon. It provides comparable entry-signal evidence, not a paper replication.

Both are offline research. They have no broker adapter. Results are not eligible for live promotion.

## Run commands

Run from the repository root with Python, numpy, pandas, pyarrow, pytest and PyMuPDF for the optional local paper extraction. These libraries were already installed.

```powershell
python -m pytest research/41_ssrn_4631351/tests -q
python -m research.41_ssrn_4631351.minute_audit
python -m research.41_ssrn_4631351.candle_run
python -m research.41_ssrn_4631351.verify_results
python -m research.41_ssrn_4631351.run
```

Both evaluation entrypoints reject an existing `initial-v1` run directory. Preserve the recorded outputs. To rerun independently, copy the track to a separate research location and choose a new run name/output directory in that copy. Do not erase evidence to force a rerun.

Saved outputs are `candle-runs/initial-v1` and `runs/initial-v1`. The candle folder contains a frozen plan, per-name coverage, daily capital ledgers, all closed trades, aggregates and accounting verification. The quote folder contains input manifests, code snapshots, plans and session trade ledgers. The whole minute-file audit is separate from the selected-six evaluation.
