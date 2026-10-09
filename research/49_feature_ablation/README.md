# Price, volume and peer-feature comparison

This track holds model complexity constant while adding candidate information. Fixed ridge alpha100 with training-only normalization compares four nested feature sets on the same shared45 rows and5/15/30-minute targets. It is a feature-information test, separate from tree and neural complexity comparisons.

The baseline contains price-derived statistics and VWAP deviation. VWAP itself uses cumulative volume, so it is not a volume-free control. The next set adds local and historical same-slot volume ratios; another adds synchronized peer/residual movements; the full set adds gap and clock information. Features differ, but cohort, targets, account schedule and costs do not.

Models fit2022-2023. Validation2024 is reported without selecting parameters, thresholds or models. Every predefined version is evaluated on2025-2026 with the fixed2bps net gate and2/5bps-per-leg account sensitivities. Training-mean forecasts are mandatory controls. Saved coefficient/scaler state permits exact numeric replay.

```powershell
python -m unittest discover -s research/49_feature_ablation/tests -v
python -m research.49_feature_ablation.run
```

Existing evidence refuses overwriting. This shares the candle-reference execution, survivor sample and ex-post full-session coverage limits in track45. None of these runs places real orders or changes production settings. Results appear in findings.md when the frozen run completes.
