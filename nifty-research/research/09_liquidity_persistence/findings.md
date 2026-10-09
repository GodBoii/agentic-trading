# Findings from sampled liquidity persistence

Initially ran October 1, 2026, then independently reviewed and corrected October 2. The original parse streamed 7,310,996,372 bytes of unchanged raw 200-depth files from four long-coverage dates. It parsed 719,034 separate-side packets and produced 85,578 valid fixed-second snapshots. The recorded source hashes match study 01, and current source sizes and modification times still match those audits. Fifteen tests pass, including actual packet freshness, cache provenance rejection, future-packet invariance and resets on recorder restarts, gaps and missing sampled observations.

The original minute aggregation overwrote actual packet receipt time with grid time. Two minutes passed its two-second boundary rule even though the oldest side was 2.153 and 2.461 seconds old at decision time. The correction retains both grid and packet timestamps and applies the decision-age limit to the oldest side. It removes those two complete minutes and the historical/future windows that depend on them. All previous artifacts and source remain under `artifacts/revisions/pre-freshness-fix`.

| Date | Valid sampled seconds | Stale-side rejections | Crossed-pair rejections | Mean deep levels above 300 units |
|---|---:|---:|---:|---:|
| August 3 | 20,705 | 141 | 49 | 121.9 |
| August 19 | 19,972 | 23 | 12 | 121.7 |
| August 20 | 22,437 | 30 | 23 | 130.2 |
| August 21 | 22,464 | 18 | 4 | 102.3 |

The fixed threshold of 300 units identifies roughly 102 to 130 levels at once. It does not select a small set of exceptional institutions. Distance and duration are necessary descriptions even before asking whether a wall forecasts a move.

The corrected study retained all 33 response trials and 54 same-cohort persistent-versus-control comparisons. There are 1,362 eligible-history outcome minutes at one minute, 1,344 at three minutes and 1,326 at five minutes, before each signal's magnitude filter. These are overlapping observations on four selected dates, not an independent sample of thousands of trading decisions.

| Signal | One-minute signed response bps | Three-minute signed response bps | Five-minute signed response bps |
|---|---:|---:|---:|
| Near depth within ten points | 0.2909 | 0.4262 | 0.4989 |
| Top five depth levels | 0.0047 | 0.0218 | 0.0144 |
| Deep count above 300 units | 0.2109 | 0.4510 | 0.5941 |
| At least 650 units, observed for ten seconds | 0.0297 | 0.0707 | 0.1385 |
| At least 650 units, observed for thirty seconds | -0.0011 | 0.1003 | 0.1889 |
| At least 650 units, observed for sixty seconds | 0.0259 | 0.1236 | 0.2279 |
| At least 1,300 units, observed for sixty seconds | -0.0120 | 0.0748 | 0.1280 |
| At least 650 units, observed for less than five seconds | 0.2109 | 0.3320 | 0.3326 |

These are conditional signed midpoint returns before any costs. Different signal rows activate on different minutes, so the raw means cannot rank trading policies. The same-cohort comparisons are the relevant control. All eighteen persistent-versus-near-depth comparisons favour simple near depth. Persistence sometimes beats the top-five control, but that does not establish an improvement over the stronger near-price measure.

The hypothesis that longer-lived near-price aggregate levels give a stronger directional signal did not hold in this run. Short-lived quantity can accompany immediate price movement, while a continuing large level can simply rest without moving price. The data cannot identify which explanation applies to a specific order owner. A fixed-price level may contain replacement orders, and subsecond disappearances can occur between sampled observations.

All adjusted p-values are 1.0. With four dates, the smallest one-sided exact daily sign-flip p-value is 1/16, already above 0.05 before correction. The test therefore cannot establish a 0.05 family-level result. Positive bootstrap intervals for some controls are descriptive only, with independence and symmetry unverified. This low resolution is a limit of the archive; it is not a proof that every effect is zero.

Near-price imbalance deserves a frozen follow-up because it also helped the one-minute regression in study 02. The current persistence filter should not be promoted as a confirmed improvement. A useful next experiment would estimate book replenishment and price resistance jointly after pressure events, with reliable trade classification and new dates. This experiment does not reproduce the original papers' individual-order event models or test execution profitability.

The full tables and all exact-cohort differences are in ignored local `artifacts/results.json` and `artifacts/report.md`. The seconds cache permits rerunning the analysis without reparsing the 7.31 GB source archive. Reuse now checks its digest, audit digest, parser definitions, shared reader, manifest and current raw-file size/mtime. It does not rehash raw bytes at every reuse. The original cache had no historical checksum, so its one-time adoption is explicitly recorded as review-based provenance, with unchanged extraction definitions and archived original code. This limitation is preserved in `cache-provenance.json` rather than claiming stronger historical integrity.
