# Replay boundary review

Reviewed and rerun on October 2, 2026.

The replay now rejects a delayed-entry quote when the selected security ID has a different expiry, strike or option type. It raises a ValueError with the security ID, before replacing prices or opening conditional exposure. The shared mark-to-market function already checks the same identity fields at exit.

Nonfinite forecast signals increment `invalid_signal` and skip the decision before quote lookup. They cannot accidentally choose a bearish contract when a NaN comparison evaluates false.

Nine focused tests pass, including one identity-change case for each contract field and three nonfinite signals. The 24 quote configurations and 72 cost scenarios completed. Both generated JSON artifacts are byte-for-byte unchanged, with no numerical changes. All 24 configurations retain negative base-slippage conditional net P&L.

Prior `results.json`, `ledger.json` and the generated report are preserved under `artifacts/revisions/pre-review-fix`.

- Results SHA256: `378507f6b3c01cb8b2a3cf043aff2e53d5c681ed6ebcc9a8a5d7374fb79f9376`
- Ledger SHA256: `b74037edf677819e246050ecadb367d5e38e102df3a6df29c2993e5531e6be05`

This check protects contract identity and finite decision evidence. Conditional bid/ask replay still does not establish actual fills, size or market impact.
