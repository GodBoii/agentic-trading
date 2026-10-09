# Quote flow and depth horizons

This study asks whether observed top-quote changes, queue imbalance, shallow depth, deep depth or persistent pressure improve Nifty futures return forecasts over 1, 3, 5 and 10 minutes.

Run from the Trader workspace with the installed research dependencies:

```powershell
python nifty-research/research/02_orderbook_horizons/study.py
python -m pytest --import-mode=importlib nifty-research/research/02_orderbook_horizons/test_study.py -q
```

Outputs are local, ignored artifacts. The program reads the first study's validated minute cache and manifest, then reparses raw Full quote packets. It checks their SHA-256 hashes against the manifest. It does not contact a broker or change raw files. Its default input remains `research/01_depth_forecast_baseline/artifacts`.

## Sources and hypotheses

Original sources were read on October 1, 2026.

- [Cont, Kukanov and Stoikov, The price impact of order book events](https://arxiv.org/html/1011.6402). Their best-quote OFI describes contemporaneous price impact. This study tests whether previously observed flow forecasts future returns, a different question. Positive flow denotes bid additions or ask removals. Broker snapshots may omit intermediate exchange changes.
- [Gould and Bonart, Queue imbalance as a one-tick-ahead price predictor](https://arxiv.org/html/1512.03492v1). Their empirical setting is Nasdaq event-level data and next-price-change classification. Here the outcome is a fixed-minute Nifty futures return. This is a transfer test, not a reproduction of their reported accuracy.
- [Stoikov, The micro-price](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694) and [the author's implementation and sample data](https://github.com/sstoikov/microprice). His microprice fits transition behaviour. The quantity tested here is the simpler weighted midpoint. No claim is made that this replicates the full estimator.
- [sauloduttra/ofi-signal](https://github.com/sauloduttra/ofi-signal). Inspected as an implementation reference for piecewise OFI. Its demonstrations use a synthetic book with embedded pressure. Those results do not transfer to Nifty or establish a live forecasting advantage. No repository code was executed or copied.

## Formulas

For successive observed quotes, bid price `b`, ask price `a`, bid size `B`, ask size `A`:

```text
e_t = B_t I(b_t >= b_prev) - B_prev I(b_t <= b_prev)
    - A_t I(a_t <= a_prev) + A_prev I(a_t >= a_prev)
OFI_minute = sum(e_t)
normalized_OFI_minute = OFI_minute / mean((B_t + A_t) / 2)
five_minute_OFI = sum(last 5 normalized_OFI_minutes)
queue_imbalance = (B - A) / (B + A)
weighted_midpoint = (a B + b A) / (B + A)
weighted_midpoint_bps = 10000 (weighted_midpoint / midpoint - 1)
depth_imbalance = (sum bid size - sum ask size) / total size
target_h = 10000 log(midpoint at t+h / midpoint at t)
```

OFI and trade-side volume estimates are different. Size removal includes trades and cancellations, without identifying either. Depth by fixed price distance and reciprocal-distance weighting comes from the first study. Rolling depth persistence uses three- and five-minute means and a one-minute difference. Individual-order lifetimes cannot be inferred from these measures.

## Experiment design

Eight feature groups across four horizons give 32 fitted configurations. Zero return and scaled one-minute momentum add eight baseline configurations. All 40 configurations are reported. Hyperparameters are fixed, with no best-horizon selection. Expanding training uses only previous dates. Every prediction needs six contiguous, complete history minutes; labels cannot cross gaps, resets, partial minutes or contracts. Raw quote flow resets on capture gaps above ten seconds, security changes, cumulative-volume resets or recorder sequence resets.

All models at a horizon share the same finite-feature rows. This prevents a model from getting credit simply because it predicts easier dates. Scalers are fit inside each training fold. Uncertainty resamples complete held-out days. The 28 comparisons against price-only receive Holm adjustment using exact daily sign-flip tests. This is exploratory because dates are few and may be dependent. Reusing the archive for other studies also creates research selection risk.

The study does not simulate fills, hedge options, or turn forecasting metrics into a trading-profit claim. Results belong in `artifacts/report.md` and `artifacts/results.json`; `findings.md` records the actual run.
