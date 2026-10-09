# Shared causal minute-history dataset and account

Tracks 46-49 share one stock cohort, chronology, feature availability and cost model. This makes model differences measurable without changing their evaluated observations.

The twelve stocks are selected by descending median 2022 daily traded value among available minute histories with at least150 complete eligible sessions. The selected IDs and all selection-source hashes are frozen before later feature construction. This remains a current-survivor/download sample, not a historical complete exchange universe. The dataset uses2022-2023 for base fitting,2024 for validation and2025 onward for evaluation. Later-data availability does not choose stocks. New model training never makes these previously available dates a pristine prospective holdout.

Each session requires375 unique regular-minute buckets with valid OHLC and volume. Weekend sessions are excluded, without a full historical exchange-calendar validation. Ex-post full-session admission is a coverage bias, and cannot be used as a live entry gate. Timestamp seconds are floored to minute buckets; original candle-label semantics and publication delays remain unverified.

Twenty-one proposed decision times are sampled every15 minutes from09:45 through14:45. A candle starting at minute t is considered completed at t+1. Its model decision reserves slots/capital then, entry uses the open at t+2, and exits use the open5,15 or30 minutes after entry. This explicitly budgets one minute after decision availability. Actual latency, spreads and capacity remain unknown. Missing feature history, zero historical volume baselines and inadequate peer coverage can remove rows. Every model uses the same admitted rows, and labels are descriptive outcomes rather than model input.

## Inputs and formulas

Own-stock features include return over1/5/15/30 completed minutes,30-minute return volatility and path efficiency, candle body/range, cumulative typical-price session VWAP deviation, local volume relative to strictly preceding minute volume, and session movement. A30-by5 sequence contains completed one-minute return, body, range, log1p local volume ratio and VWAP deviation.

Same-slot relative volume divides the current minute's volume by the average at that minute in up to20 strictly previous eligible sessions, requiring at least5. No current-day volume enters its own historical baseline. Within each session, early sequence volume ratios use all preceding available minutes up to30. No sequence crosses a session boundary.

Peers use the equal-weight return of other eligible stocks at the same completed-minute time, with at leastfour peers. Residual return subtracts that basket from the stock's return. This is a peer-stock proxy, not a true index, sector or hedge. Overnight gap actually compares current open with the last eligible full session's close within seven calendar days; if an intervening session was excluded, it can span that session. That naming limitation is disclosed rather than treated as a genuine one-session gap.

## Account behavior

The shared deterministic simulator begins each evaluated date with Rs500,000. It reserves up toRs100,000 and one slot at each admitted decision, with at mostthree simultaneous pending/active positions and one position per stock. Simultaneous decisions rank by estimated net edge and then security ID. Capital stays reserved until scheduled exit; fully collateralized shorts do not create extra buying power.

The admission score is absolute gross-return forecast minus estimated flat-price fees at the already observed decision price, minus two legs of adverse execution cost. The default additional net-edge threshold is2bps. Actual fill reference prices are future candle opens used only after order admission. Integer-share fills charge the frozen fee model on each side. Costs of2 and5bps per leg are sensitivities, not measured spreads. There is no fake depth or fill-capacity claim.

New decisions and arriving pending entries stop after realized daily loss reaches Rs2,500. Existing positions still exit at their scheduled horizon. This is a realized-loss entry halt, not a guaranteed maximum loss or intratrade stop. Account invariants reconcile capital, fees, reservations, slot limits and complete exits. There are no bid/ask observations, intratrade liquidation marks, broker square-off integration, shortability or impact calibration.

## Reproduce

```powershell
python -m unittest discover -s research/45_market_dataset/tests -v
python -m research.45_market_dataset.dataset
```

The build refuses to overwrite its cache. A new specification/cache version is required for a repeat or change. load_dataset returns the aligned rows DataFrame, a memory-mapped sequence array and a fingerprinted manifest. The cached market derivatives remain local; compact specifications/manifests are versioned. Original files remain read-only.

Tests cover feature/sequence prefix invariance, session validity, timestamp flooring, delayed fills, slot and capital reservations, no overlapping stock exposure, loss halts and adverse costs on both sides. Tests prove these implementation behaviors, not profitability.
