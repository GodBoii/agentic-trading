# Expiry and premium mechanics

This independent study tests captured option-price shapes, fixed-strike premium compression and expiry-distance summaries. It builds on study03's parity-valid quote observations and reads the shared option and futures caches. It does not fit a variance forecast or place orders.

- [Report](report.md) explains the findings and their limits.
- [All numerical tables](artifacts/numerical-results.md) retain the populated DTE and horizon comparisons.
- [Results JSON](artifacts/results.json) includes every status, date-level mean, input hash and quote-shape family.
- [Sources](sources.md) records papers and primary repository references reviewed.

From the Trader directory:

```powershell
python nifty-research/research/12_expiry_premium_mechanics/study.py
python -m pytest --import-mode=importlib nifty-research/research/12_expiry_premium_mechanics/test_study.py -q
```

The script writes only this folder's artifacts. Inputs are read-only. Receipt time does not establish exchange quote age. A conditional bid/ask-bound flag does not establish executable arbitrage, capital capacity or actual fills.
