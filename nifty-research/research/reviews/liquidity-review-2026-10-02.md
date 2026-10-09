# Independent liquidity review, October 2, 2026

Reviewed studies 02 and 09, the preserved study 01 package, source audit metadata, registry paths and the frozen nearby-depth model. Changes in this review are limited to study 09 and this file. No broker APIs, remote services or archive records were changed.

## Corrected findings

Study 09 used grid time as `source_at` in its minute aggregation. Its reported two-second packet freshness gate therefore admitted two minutes whose oldest side was 2.153 and 2.461 seconds old. The affected decisions were August 3 at 06:25 UTC and August 19 at 04:48 UTC. The fix keeps `grid_at`, actual newest `source_at` and `oldest_source_at` separate and checks the oldest side at decision time.

The rerun retains all 33 response trials and 54 exact-cohort controls. Valid labelled minutes decrease from 1,376/1,362/1,348 to 1,362/1,344/1,326 for one/three/five minutes. Near-depth signed returns change to 0.2909/0.4262/0.4989 bps. All eighteen persistent-versus-near-depth comparisons still favour near depth. All adjusted p-values remain 1.0. These are descriptive responses before costs, not strategy profits.

The previous study source, tests, findings, seconds cache, audit records, results and report are preserved in `09_liquidity_persistence/artifacts/revisions/pre-freshness-fix`. No source reparse was needed because the seconds cache already retained actual packet timestamps and side ages.

Cache reuse previously accepted arbitrary seconds files alongside stale audits. It now checks parquet/audit digests, source manifest, extraction definitions and the shared reader. It also rejects missing actual timestamp fields, invalid packet ages and changed source size/mtime. Reuse does not hash the full raw archive again. The legacy cache originally lacked a checksum. Its one-time adoption records that limitation explicitly and verifies identical archived/current cache bytes, unchanged extraction definitions, the archived study code hash and matching source audits. New raw parses create provenance directly.

Study 09 now records the imported study 02 uncertainty-code hash as well. Extraction hashes allow changes confined to analysis without claiming that changed parsing is compatible with the old cache.

## Cleared checks

- The final targeted run passes 28 tests across studies 02/09 and programme tests. Study 09 has 15 tests, including the new actual-packet freshness and provenance rejection cases.
- Original study 02 code matches its saved code hash. Its recorded source-feature hash matches study 01's cache. Raw audit hashes match the baseline manifest, and current raw-file sizes/mtimes match the saved audits.
- Accepted study 02 feature cohorts have a maximum quote age of 1.795 seconds. Cached backward depth matches are strictly earlier than decision time and at most 1.939 seconds old.
- Date/segment/contract grouping retains date columns. Historical and future completeness checks exclude missing minutes and restart boundaries. The fixed-second persistence calculation uses earlier packets only and resets on missing samples. It measures continuous sampled aggregate level presence, not individual-order survival.
- Study 02 compares identical finite-feature cohorts within each horizon. Study 09 pairs controls on the exact persistent-signal cohort. Holm corrections retain the declared 28, 33 and 54 comparison families. No global cross-study significance claim follows from separate family corrections.
- All ten original package hashes match study 01's source snapshot. All seven artifact hashes recorded in its provenance match the preserved artifacts. The current shared implementation differs only in `__main__.py`, consistent with the changed output location.
- The frozen hypothesis's feature source and study 02 code hashes match. Refitting both frozen models reproduces all scaler means, coefficients and intercepts exactly, with 2,592 training rows. The frozen PRICE/NEAR features match the current study definitions. Its final fit uses 31 extra rows versus the all-feature study 02 cohort because it needs only PRICE and NEAR; this is coherent for the frozen pair and should stay explicit.

## Remaining corrections outside this ownership

1. `freeze_hypothesis.py:44` fingerprints study 02 but omits `nifty_lab/ingest.py`, `io.py` and configuration values that define the cached depth/price features. The current coefficients are consistent, but future feature drift could evade the declared frozen feature-code hash. Include those dependency hashes and exact feature/preprocessing settings in the prospective freeze; do not silently retrain or overwrite the original historical bundle.
2. The study 01 registry entry lacks a `report` field although its report is `artifacts/report.md`. Generic consumers that default to `report.md` resolve a missing path. Add the explicit field. Study 05 also relies on the default rather than an explicit report path, although its current root report exists.

Raw sources were not fully rehashed during this review. Source-byte hash matching here verifies prior audited provenance and current size/mtime, not protection against an adversarial same-size edit that restores mtime. Independent fresh sessions and execution-aware evaluation remain required.
