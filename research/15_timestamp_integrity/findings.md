# Recording integrity findings

October 1, 2026. The archive can recover real best-level depth quantities, but it cannot establish absolute last-trade time or quote age for these sampled packets. Every archived trade time is a bare clock string with unknown historical decoder semantics. Selective raw capture also prevents complete-session reconstruction.

## Completed audit

The cohort is the same twelve NSE cash instruments selected from August 18 historical ADV. The audit reads the first selected packets in sorted file order on August 28, August 31 and September 1, capped at 20,000 per date. This is a convenience sample, not a representative session distribution.

| Date | Selected packets | Capture scope | Normalized | Rejected | Missing LTT | Absolute trade time unknown | Quote event time unknown |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| August 28 | 20,000 | Unknown | 20,000 | 0 | 0 | 20,000 | 20,000 |
| August 31 | 362 | Hot only | 362 | 0 | 0 | 362 | 362 |
| September 1 | 177 | Hot only | 177 | 0 | 0 | 177 | 177 |

August 28 reaches the cap. The other dates exhaust their available selected cohort packets. All 20,539 selected packets pass this full-book validation, but a valid depth message does not prove source freshness. No sample has original wire bytes, recorded quote timestamp or source sequence. August 28's absent scope field stays unknown. The other 539 packets explicitly retain hot-only scope, which selects periods based on contemporaneous system interest.

Seventeen behavioral tests pass and Python compilation passes. Tests cover ambiguous and missing times, explicit epoch and aware datetime parsing, signed negative offsets, separate timezone sensitivities, venue/identity mismatches, malformed and crossed books, quantity integrity, frozen records, original binary epoch preservation and refusal to accept invented quote metadata. Synthetic binary tests validate only the documented parser path; the archive contains decoded JSON.

## Why previous age arithmetic needs a label

The [official protocol](https://dhanhq.co/docs/v2/live-market-feed/) supplies last-trade epoch in a full binary response. The [current official SDK](https://github.com/dhan-oss/DhanHQ-py/blob/main/src/dhanhq/marketfeed.py) formats it as a UTC clock without the date. Our archive's historical SDK version and any transforms are unrecorded. Its tokens resemble local receipt clocks, so attaching today's SDK interpretation would also be an assumption.

The normalizer therefore preserves raw LTT and parsed clock text while leaving its absolute epoch and signed receipt-minus-trade offset unknown. The two columns below deliberately impose different same-date timezone assumptions. Neither is a network-latency measurement, and neither timestamps the order book.

| Date | Median offset if bare time is same-date IST, seconds | Negative offsets under IST assumption | Median offset if same-date UTC, seconds | Negative offsets under UTC assumption |
| --- | ---: | ---: | ---: | ---: |
| August 28 | 2.54 | 0 | -19,797.46 | 20,000 |
| August 31 | 71.17 | 7 | -19,728.83 | 362 |
| September 1 | 89.70 | 0 | -19,710.30 | 177 |

The timezone assumptions differ by 19,800 seconds. We retain the seven negative IST offsets instead of clamping them. These values cannot resolve whether the historical decoder used local or UTC clocks, whether its date was correct, or whether receipt/source clocks were synchronized. Selecting whichever assumption looks freshest would conceal missing provenance.

## Aggregate depth is not best-quote size

Every accepted packet has greater aggregate five-level quantity than its best-level quantity on both sides.

| Date | Median five-level quantity divided by best bid quantity | Median ratio on ask side | Rows where 10% of aggregate exceeds full best bid quantity | Same comparison on ask side |
| --- | ---: | ---: | ---: | ---: |
| August 28 | 10.94 | 12.86 | 10,479 of 20,000 | 11,409 of 20,000 |
| August 31 | 12.66 | 15.34 | 213 of 362 | 222 of 362 |
| September 1 | 18.73 | 11.85 | 116 of 177 | 98 of 177 |

The earlier engine's ten-percent aggregate-depth cap can therefore allow more quantity than displayed at the best quote. It never claimed to model best-level capacity, and this audit quantifies the gap. These selected raw packets cannot retroactively repair every derived replay observation. Any future execution model should use actual level quantities for a depth-limited aggressive sweep, and keep displayed liquidity distinct from guaranteed future fills.

## Evidence and architectural changes supported

`runs/initial-v1/plan.json` freezes sample limits, dates, cohort, code hashes and timing assumptions. `audit.json` records file manifests and validation diagnostics. Three `normalized-<date>.jsonl` files retain 20,539 immutable-contract observations with source file and row positions. `verification.json` confirms saved source hashes, original file hashes, output hashes, unknown-time preservation and separate best/aggregate quantities. The sample has zero observed receipt-order backsteps or duplicate receipt/instrument identities, which does not guarantee future streams will share those properties.

Before new alpha claims, record original binary bytes, full integer trade epoch, decoder version and hash, UTC and monotonic receipt clocks, session/reconnect IDs, local receipt sequence, predefined cohort and scope, queue drops, parse errors and clock synchronization evidence. Record every packet received for the cohort. Do not infer all-packet coverage from a file merely existing. The reviewed feed does not supply quote event age, so that field must remain unknown unless another verified source provides it.

The binary normalizer is ready for an offline future archive with exact epoch provenance. It does not open a live socket or modify the recorder. No trades, strategy results or production settings changed in this infrastructure study.
