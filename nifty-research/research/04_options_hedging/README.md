# Option structures and hedging

This study compares twelve fixed option structures at three intraday holding periods using archived Nifty quotes. It also runs a separate synthetic delta-hedging experiment. Neither experiment places orders.

From `nifty-research` run:

```powershell
python research/04_options_hedging/study.py
python -m pytest research/04_options_hedging/test_study.py -q --import-mode=importlib
```

Inputs are read from `research/01_depth_forecast_baseline/artifacts`. Outputs remain in this folder. `artifacts/results.json` contains every trial, `ledger.json` retains contracts and unresolved positions, `paired-hedge-comparisons.json` compares shared entry times, and `synthetic-hedging.json` contains the simulated experiment. `provenance.json` records SHA-256 hashes of the derived inputs.

The twelve structures are long call, long put, long straddle, short straddle, long strangle, short strangle, bull call spread, bear put spread, iron condor, iron butterfly, bull put credit spread and bear call credit spread. Each is tested at five, fifteen and thirty minutes. These are 36 exploratory configurations, not 36 independent research findings.

Read [the report](report.md) and [sources](sources.md).
