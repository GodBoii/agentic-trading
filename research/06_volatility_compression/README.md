# Volatility compression and expansion research

This track asks whether quiet completed-minute quote closes followed by directional range expansion give enough net continuation to cover trading costs. It tests two Bollinger-width rules and a compressed price channel. These are method adaptations, not faithful published strategy replications.

## Sources reviewed

- [John Bollinger's confirmed-breakout manual](https://www.bollingerbands.com/_files/ugd/58be43_d09c50b6e8ea4afd9af0523ef94de876.pdf). It defines twenty-period mean bands at two standard deviations, identifies a squeeze by a 125-period BandWidth low, and uses two consecutive closes outside bands. Its method also uses ADX to interpret alerts; we omit ADX and therefore do not claim a Method IV replication. Its warning about insufficient observations in short bars is especially relevant to our incomplete received tape.
- [QuantConnect LEAN BollingerBands implementation](https://github.com/QuantConnect/Lean/blob/master/Indicators/BollingerBands.cs). Reviewed band and normalized width definitions. Our code independently computes them with Python's population standard deviation and does not execute downloaded repository code.
- [Fang, Jacobsen, and Qin, August 2014 working paper](https://acfr.aut.ac.nz/__data/assets/pdf_file/0007/29896/100009-Popularity-vs-Profitability-BB-August-Final.pdf). Their international daily-market study reports weakening Bollinger predictive power over time and examines squeeze variants among robustness checks. It is a reason to test current net execution economics, not evidence that our intraday NSE adaptation must lose.

## Formulas and causal timing

For the latest twenty completed observed minute closes, m is the arithmetic mean and s the population standard deviation. Upper and lower bands are m + 2s and m - 2s. Normalized bandwidth in basis points is 4s/m times 10,000. The relative squeeze compares current width against the minimum of 125 strictly prior widths. The absolute squeeze instead requires width at most fifteen basis points. A squeeze arms the rule for ten completed bars. Two consecutive completed closes outside their respective evolving bands and the shared three-basis-point buffer trigger a directional signal.

The channel variant compares a completed close with the high and low of the five strictly preceding completed observed closes. It requires that prior channel width be at most fifteen basis points and a breakout beyond the shared buffer. This is a close-channel adaptation, not a high/low Donchian bar reproduction.

A minute close becomes known only when a later receipt enters the next minute. The signal timestamp and reference midpoint belong to that later receipt. A reversal beyond the buffer at decision time blocks entry. The first observed minute may be partial; no OHLC completion is invented. Each stock maintains separate history. A receipt gap above fifteen seconds or unusable data clears all rolling state. There is no forward filling of missing minutes. This reduces samples but preserves the meaning of continuous observation.

No volume, realized trade flow, ATR, ADX or tick-level queue information is synthesized. The shared execution model uses later bid/ask observations with fees, slippage, cash and risk limits. Minute smoothing cannot substantiate exchange-level HFT.

## Reproduce

From the repository root, run `python -m unittest discover -s research/06_volatility_compression/tests -v` and `python -m research.06_volatility_compression.run`.

Inspect `runs/initial-v1` for frozen settings, manifests, trades and comparisons. Strict-mode data failures and receipt-proxy sensitivity are reported separately. The latter assumes source quote usability from receipts and cannot support promotion.

## Next useful research

Collect source-age evidence and continuous tapes before reducing the continuity gate. Extend to several months with predeclared widths and holding periods. Measure whether compression predicts larger absolute moves separately from whether the observed breakout direction predicts profitable continuation. Larger volatility alone is not directional edge. Use independent future days rather than searching this seven-session tape for a winning parameter combination.
