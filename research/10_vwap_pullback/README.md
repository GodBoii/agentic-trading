# VWAP pullback and reclaim

This track asks whether a directional impulse, a later pullback and a still later recovery provide net continuation returns. It uses an explicit setup state machine. A price below VWAP by itself never triggers a long entry. Both rules were frozen before their first replay on October 1, 2026; the poor results from other families did not tune these thresholds.

Run `python -m research.10_vwap_pullback.run` from the repository root. Run tests with `python -m unittest discover -s research/10_vwap_pullback/tests -v`.

## Frozen sequence

1. Observe six completed one-minute midpoint bars. Over their five-minute span, require VWAP slope of at least 1 bps and midpoint movement of at least 8 bps in the same direction. The last close must be 10 to 80 bps beyond its recorded VWAP. Arm a long or mirrored short setup.
2. In a later completed bar, require a pullback. Reclaim uses signed close/VWAP deviation from -5 to +5 bps. Bounded pullback uses +2 to +10 bps and stays on the trend side of VWAP.
3. In a still later completed bar, confirm recovery with at least 3 bps one-bar directional movement and signed deviation of at least 8 bps for reclaim or 15 bps for bounded pullback. Emit a signal on the receipt of the following minute's quote.

Expire the whole setup after five bars from arming. A reversed VWAP slope, deviation below -10 bps or above +100 bps invalidates it. Missing VWAP in any of the six completed bars, an unusable quote, a gap over 15 seconds, incomplete bars or excessive current spread clear the setup. Arming, touching and confirmation happen on different completed bars. New order fills require later observations in the common engine.

Targets, stops, holding time, cooldown and account limits match the two other assigned tracks: 30 bps target, 20 bps stop, 600-second horizon/cooldown, 5 bps maximum spread and cost-room admission. Bar edge coverage and minimum observed quote counts match the causal bar helper. Each track saves a private helper for complete source snapshots.

## Sources and interpretation

- [QuantConnect official intraday VWAP guide](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/intraday-vwap) and [LEAN indicator implementation](https://github.com/QuantConnect/Lean/blob/master/Indicators/IntradayVwap.cs). The implementation distinguishes valid trade/volume input, daily resets and readiness. We inspect these semantics, but use recorded VWAP rather than fabricate weights from quote counts. No remote code runs here.
- [Busseti and Boyd, VWAP optimal execution](https://arxiv.org/abs/1509.08503). The paper minimizes benchmark slippage subject to uncertain market volume and transaction costs. It is an execution study, not evidence that a VWAP crossing predicts price. Our continuation hypotheses do not reproduce its volume schedule.
- [Barzykin and Lillo, optimal VWAP execution under transient impact](https://arxiv.org/abs/1901.02327). This paper reinforces the distinction between benchmark execution and alpha. Its impact-aware scheduling is absent from our simple all-or-none aggressive fill proxy.

VWAP is `sum(trade_price * trade_volume) / sum(trade_volume)` over a defined interval. A quote midpoint is not a trade price and quote count is not trade volume. The recorded VWAP field's weighting, source latency and session reset remain unverified. All strategy thresholds are newly stated research hypotheses, not formulas for institutional profitability.

## Evaluation

Use the August18 prior top-12 ADV universe, development August19/20/21, validation diagnostics August24/25 and historical audit August31/September1. Every date has already been observed by earlier work; no untouched holdout exists. Run strict metadata admission and an explicit unverified receipt-proxy sensitivity. Retain both zero-trade and losing results. All variants remain ineligible for promotion.
