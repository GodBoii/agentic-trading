# Controlled monthly adaptation

This track compares a fixed ridge predictor with monthly expanding-history fitting, rolling 12-month fitting, recency weighting and a controlled update gate. All use the same 21 causal features, stock cohort, delayed execution references and account rules from `research/45_market_dataset`.

The primary horizon is 15 minutes. The four ridge schedules also run at 5 and 30 minutes. Hyperparameters, windows, costs and update conditions were declared in `hypotheses.json` before dataset outcomes were evaluated.

The controlled method begins with the static model. At a monthly boundary it checks the previous 60 observed trading dates. It compares the actual deployed model only when those dates are entirely later than its final training label. Candidate models train strictly before that validation block. A switch requires at least 1% lower validation MAE and nonnegative validation account utility no worse than the incumbent. Without a qualifying candidate, the model coefficients remain unchanged. After a switch, validation must accumulate 60 fresh dates before another update can qualify.

This constraint is deliberate. Scoring a model fitted last month on a 60-day block that contains its own training observations would make the comparison unreliable. The gate therefore logs decisions every month while accepting updates less often.

Every switch records the shadow-model hash and the separately refitted deployment-model hash. Monthly forecasts use immutable coefficients. Adaptation is an offline chronological simulation; it has no broker client or production-setting changes.

`sources.md` distinguishes this simple experiment from DoubleAdapt's learned adapters and meta-learning. `findings.md` reports the completed results. No method beat zero-return prediction on later MAE or RMSE, and the controlled gate accepted zero updates.

Run from the repository root after the shared dataset cache is complete:

```powershell
python -m pytest research/48_controlled_adaptation/tests -q
python -m research.48_controlled_adaptation.run
python -m research.48_controlled_adaptation.verify
```

The runner rejects an existing `runs/initial-v1` directory. Preserve saved evidence rather than overwriting it. Full predictions, daily/trade ledgers, model snapshots and monthly audit records remain local under that directory. Compact summary artifacts belong under `evidence/` for review and version control.
