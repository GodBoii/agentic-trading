# Deterministic intraday research lab

This is an offline research package. It has no broker client, credential reader, network feed, or order-submission adapter. It reads existing recordings without changing them. Research artifacts stay below this directory.

The initial objective is to make causal decisions, execution assumptions, account constraints, and costs inspectable before considering live integration. This is a minute-scale momentum baseline, not an HFT implementation or a profitable strategy.

## Run from the repository root

The installed Python environment already supplies pandas, NumPy, and PyArrow. Dependency requirements are recorded in `requirements.txt`.

```powershell
python -m unittest discover -s research/intraday_lab/tests -v

python -m research.intraday_lab --dates 2026-08-19 2026-08-20 2026-08-21 2026-08-24 2026-08-25 2026-08-31 2026-09-01 --count 12 --output research/intraday_lab/runs/my-strict-run
```

Each output directory must be new and must resolve inside `research/intraday_lab/runs`. Existing evidence is never overwritten. The default universe is the August 18 recorded universe, sorted by historical ADV. Its date must precede every replay date. Missing ADV does not become an arbitrary tie-broken instrument choice.

For a separate sensitivity experiment:

```powershell
python -m research.intraday_lab --dates 2026-08-19 2026-08-20 2026-08-21 2026-08-24 2026-08-25 2026-08-31 2026-09-01 --count 12 --receipt-proxy --output research/intraday_lab/runs/my-proxy-run
```

`--receipt-proxy` permits unknown recorded freshness flags and does not require a recent last trade. It still rejects explicitly false freshness/warmup flags, invalid quotes, and insufficient continuous history. It assumes that received quote observations can be used for research. Source quote event time and actual quote freshness remain unverified. Its P&L must never be cited as validated strategy performance.

## What is built

| File | Responsibility |
|---|---|
| `domain.py` | Immutable market, policy, account, pending-order, position, and trade contracts |
| `costs.py` | Decimal arithmetic for a frozen standard NSE cash intraday fee schedule |
| `data.py` | Venue-specific ingestion, prior-date universe selection, normalized-input fingerprints, and coverage diagnostics |
| `policy.py` | Causal rolling midpoint momentum, confirmation, spread, and optional VWAP filters |
| `replay.py` | Single-account reservations, later-observation fills, bounded entry drift, cooldowns, liquidation estimates, and exits |
| `audit.py` | Raw last-trade timestamp audit with signed clock offsets and explicit capture-scope uncertainty |
| `__main__.py` | Frozen comparison plans, per-session replay, evidence files, and aggregate comparisons |
| `tests/test_lab.py` | Causality, long/short accounting, missing data, reservation limits, delayed execution, and unresolved-position tests |

The CLI freezes six comparisons before reading market outcomes:

1. Rolling midpoint momentum.
2. The same policy with VWAP alignment.
3. VWAP alignment with a gross-target-versus-cost-room rejection gate.
4. The same cost-room policy with 1,000 ms simulated order latency.
5. The same policy with 3 bps additional slippage per side.
6. The same policy with a smaller illustrative paper account and monetary risk budget.

The cost-room gate is a necessary room check, not an expected-value estimator. It does not predict whether the target will be reached. Account values are experiment scenarios, not recommended capital allocations.

## Execution and account semantics

Signals use only received observations up to the decision time. Entry requires a later observation of the same instrument at or after simulated order arrival. Even zero configured latency cannot fill on the signal observation.

Long entries use ask prices and exits use bids. Short entries use bids and exits use asks. Additional hypothetical slippage applies separately. Fees use actual simulated leg values. Spread is already included in the fill prices and is not subtracted again from P&L.

Pending entries reserve a position slot and cash. Exposure is unlevered. Size is limited by position value, planned loss including estimated fees, available cash, and a fraction of displayed aggregate depth. Limits are checked again at the simulated fill price. This last depth constraint is only a footprint proxy. It does not prove best-quote capacity.

Entries expire, cancel if prices drift beyond their permitted range, and stop at the session cutoff. Targets, stops, time exits, daily loss actions, and scheduled flattening create an exit intent that also needs a later usable observation. Daily loss limits trigger actions; they do not guarantee the final loss cannot exceed the limit after a gap or delayed fill.

Data gaps reset signal history. Unknown freshness fails closed in default mode. A stale held-instrument mark blocks additional entries. Missing future observations leave exposure unresolved. The engine never creates a convenient closing trade at end-of-file.

Each date begins with the same configured paper account. Aggregate P&L sums separate daily scenarios without reinvestment. It is not an annualized return, live equity curve, or confidence estimate. Realized P&L excludes unresolved exposure; its separate last-quote liquidation estimate may be stale.

## Evidence files

`experiment-plan.json` preserves instrument selection, thresholds, account assumptions, dates, a source-code fingerprint, and runtime versions. New runs also save an `engine-source` snapshot. `input-DATE.json` records source-file metadata, the normalized tape digest, coverage, gaps, missing fields, and trade-age distributions.

Each policy/date produces a summary and a trade CSV. `comparison.csv` and `aggregate.json` collect the outcomes. Runs are ignored by Git because manifests and raw-input references can be large. The human findings report is kept alongside the code.

Raw timestamp audit example:

```powershell
python -m research.intraday_lab.audit --plan research/intraday_lab/runs/my-strict-run/experiment-plan.json --dates 2026-08-28 2026-08-31 2026-09-01 --limit 20000 --output research/intraday_lab/runs/my-audit/audit.json
```

The audit takes the first selected packets in sorted file order. Selective historical capture can leave very few packets for the fixed universe. Its trade-time distribution is not a representative quote-latency distribution.

The first smoke run exposed an incorrect nested-ADV lookup. It remains preserved as invalid selection evidence and must not be used for strategy conclusions. Later runs correct that lookup and include a regression test.

Previously inspected historical dates are diagnostic data. They are not a pristine final holdout. Do not repeatedly optimize on these sessions and call the resulting winner validated.

## Limits that prevent live promotion

- Input is a downsampled received-observation tape, not a full order-event stream.
- A last-trade timestamp does not establish source quote age.
- Some sessions omit source freshness and connection state.
- No order-level queue reconstruction, passive fills, partial fills, or calibrated impact model exists.
- Simulated fills are all-or-none at observed quotes plus hypothetical slippage.
- Stop/target crossings between observations are unknown; delayed next-quote execution does not recover missing paths.
- The illustrative fee model rounds each simulated order. Contract-note aggregation, rounding, and account-specific tariffs require reconciliation.
- No point-in-time daily corporate-action/trading-status gate is wired into this lab yet.
- No broker rejection, durable external-order recovery, live token renewal, or multi-account service exists.
- Receipt-time replay throughput is not exchange-to-fill latency.

## Next research gates

1. Audit raw packet source timestamps against receipt timestamps and compare with the derived tape. Preserve negative clock offsets rather than clamping them into apparent freshness.
2. Capture a fixed cohort with all packets, separate quote/trade timestamps, receipt/processing clocks, queue delay, disconnects, and reference-data versions.
3. Add a reference-data contract for daily trading status, corporate actions, instrument ticks, and permitted order types.
4. Compare this exact policy on fresh, verified data before changing thresholds or introducing another model.
5. Calibrate execution using observed paper/live order timelines under an explicitly approved deployment scope. Broker integration is a separate implementation phase.
6. Reject or revise hypotheses using development data, then freeze the next experiment before opening a later evaluation period.

Every iteration should preserve the old run, explain the observed failure, state the proposed correction, add a behavior check where necessary, and produce a new run. A losing result is useful evidence. Removing it is not an improvement.
