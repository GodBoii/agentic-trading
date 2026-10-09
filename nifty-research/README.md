# Nifty research

This workspace tests whether recorded Nifty futures depth improves forecasts and option decisions. It is an offline lab. It contains no broker client, credentials, live collector, order placement or scheduled task.

## Run

From this directory:

```powershell
python -m pytest -q
python -m nifty_lab run
```

The separate stages are `prepare`, `evaluate`, `replay` and `report`. `prepare` can resume from verified per-session caches. Use `--rebuild` to regenerate derived data. Dependencies are declared in `pyproject.toml`; the laptop already has them available.

Each research topic has its own folder under `research`. The baseline's outputs are now in `research/01_depth_forecast_baseline/artifacts`. Shared code stays in `nifty_lab`. The CLI rejects output paths outside this workspace's research/artifacts directories. Original archives stay in their existing locations and are opened only for reading. Accepted inputs receive SHA-256 hashes and quarantine counts. Source sizes and modification times are checked before and after preparation.

## Experiment 1

- One-minute sampled futures quote midpoint features.
- Five-minute forward midpoint return labels inside uninterrupted session segments.
- Expanding chronological training with five prior training dates and at least 200 training rows.
- Fixed Ridge regularization, with standardization fitted only to the training dates.
- Same decision-time cohort for price-only, nearby-depth, deeper-depth and estimated-flow models.
- Descriptive day-block bootstrap for paired forecast-error differences.
- One-lot conditional replay of long calls, long puts and directional debit spreads.
- Fixed two-basis-point signal threshold, one-second latency and five-minute holding period.
- Entry and exit at the appropriate bid/ask, plus fees and additional slippage.
- Unpriced exits are recorded and stop that policy for the remainder of the date.

Changing these choices after seeing results creates a new exploratory experiment. It does not turn the initial dates into an untouched validation set.

## Read results

Start with [the research programme](research/README.md). `research/01_depth_forecast_baseline/artifacts/report.md` is the first experiment's readable report. Its `manifest.json` contains archive provenance and quality diagnostics. `forecast-results.json` includes every chronological fold and coefficient. `predictions.parquet` preserves test predictions, including rows without future labels. `option-replay-ledger.json` preserves contract identities, prices and unresolved exits. `evidence-gates.json` records remaining requirements before execution integration. `historical-agent-evidence.json` demonstrates a curated agent input with candidate identities and source times. It excludes future labels and P&L outcomes and allows only no trade or a research hypothesis.

The payoff library also includes straddles, strangles, iron condors and iron butterflies. Those structures are not automatically selected by the replay. Naked short options have no executable margin or tail-risk model here.

## Limits

The feed is sampled broker information, not a complete exchange trade tape. Signed volume is an estimate. Missing quote sizes prevent a capacity or fill claim. Option exchange timestamps, synchronized spot, IV, Greeks and historical news are absent from the saved feed. Closed-trade P&L does not measure intratrade drawdown or account margin. A few correlated dates cannot establish a production edge.

The normal-session filter excludes weekends. It is not a full NSE exchange calendar and does not assume special weekend sessions. These dates are not used for a live decision.
