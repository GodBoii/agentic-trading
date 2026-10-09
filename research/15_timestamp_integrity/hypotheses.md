# Frozen recording audit questions

October 1, 2026. Infrastructure research, no trading signal or profitability claim.

Use the fixed August 18 top twelve prior-ADV NSE cash instruments. Audit the first selected packets in sorted file order for August 28, August 31 and September 1, capped at 20,000 per date. This is a transparent convenience sample, not a representative full-day measurement.

1. Do recorded decoded packets retain enough timing provenance to reconstruct absolute last-trade time without assumptions?
2. Does capture scope establish complete cohort recording or selective hot-only capture?
3. How often does best-level quantity differ from aggregate five-level quantity?
4. Does strict full-packet validation identify malformed identity, timestamps, incomplete or crossed books?

For bare HH:MM:SS trade tokens the default absolute trade time, signed age and quote event time remain unknown. Report explicitly separate same-date IST and UTC arithmetic sensitivities, preserving negative offsets. Neither is source quote age or network latency. A synthetic binary decoder test preserves the exact wire epoch and proves future recorder feasibility, not restoration of lost historical bytes.
