# Per-row forecast audit

`row-audit-v1` adds eight Parquet ledgers covering the four original evaluation
sessions in both freshness modes. It contains 12,248 receipt-proxy rows and 31
strict-mode rows. Strict-mode predictions are null because there was no fitted
strict model. Empty strict session files preserve the same schema.

Each row records stock identity, date, freshness mode, decision timestamp,
original label entry and exit timestamps, five causal features, feature hash,
input/model hashes, realized long and short executable net-return labels, and
long and short forecasts for all seven frozen variants. `row_id` identifies the
session, mode, stock and decision time. All forecasts are in net-return bps,
not calibrated probabilities.

The supplemental script restores the original fitted parameter values without
fitting or tuning. It repeats the original label-admission rules solely to recover
row identities, proves exact feature/order agreement with the original label
function, and reproduces every saved per-session forecast diagnostic exactly.
It also hashes the original model and replay evidence trees before and after
the audit. Those original files remain untouched. `report.json` records these
checks and the SHA-256 of each ledger and the supplemental source.

The ledgers include complete future-label intervals only. They are prediction
evidence rather than trade ledgers. Account policies never used future label
completeness to admit entries. Fixed-notional labels do not apply account size,
target, stop or position-limit rules. Existing account replay evidence remains
in `runs/initial-v1`.

Run the additive audit once with
`python -m research.42_weighted_ensemble.supplemental_audit` from the repository
root. The script refuses to overwrite existing supplemental evidence. Three
additional focused tests passed with
`python -m pytest research/42_weighted_ensemble/tests/test_supplemental.py -q`.
