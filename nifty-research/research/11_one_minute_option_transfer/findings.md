# Findings from the October 2 run

The one-minute nearby-depth forecast failed to become a profitable directional option policy under the tested execution assumptions.

The study evaluated 18 fixed configurations on 1,655 forecast rows across nine previously viewed dates. Ten configurations entered positions and all ten lost after estimated charges and slippage. Eight configurations entered no positions because neither fitted forecast reached the 1 or 2 bps thresholds. Those zero outcomes are no-trade results, not profitable strategies.

At the 0.5 bps threshold, the nearby-depth long-option policy entered 152 positions. Its conditional gross P&L after bid/ask prices was Rs87.75. Estimated charges were Rs9,577.59; additional 0.10-point slippage per unit per transaction brought net P&L to minus Rs11,465.84. Extra slippage of 0.50 points brought it to minus Rs19,369.84.

The matching nearby-depth debit-spread policy entered 144 positions. Gross P&L was minus Rs2,795.00 and net P&L was minus Rs24,130.96. Its four orders per round trip cost more than a single option's two orders. Different availability and exposure schedules mean this comparison does not isolate hedging as the cause.

Price-only at 0.5 bps generated only four single-option positions and three spread positions. Their net outcomes were minus Rs1,143.63 and minus Rs672.88. Momentum was more active and all six momentum configurations lost net.

All entered positions had retained exit quotes in this run, so no missing option exits affected these totals. This does not cure the earlier underlying-forecast coverage selection. Study02 saves only labelled decisions, and these archive dates were already used to select the one-minute nearby-depth hypothesis.

Seventeen focused tests pass. They verify scheduled horizon alignment, buy/sell sides, two/four-order costs, unknown-exit exposure blocking, backward-only candidate selection, identity checks for all contract fields at entry and exit, nonfinite forecast rejection, the registered threshold boundary, the no-trade reference and bearish put selection.

The economic lesson is specific. A small one-minute forecasting improvement is insufficient for repeatedly crossing an option spread and paying order charges. The positive gross nearby-depth single-option total is tiny relative to costs and is not evidence of a usable strategy. Future work should retain all causal forecasts, measure larger expected option repricing relative to costs, and test fresh data. This result does not justify changing thresholds until a favourable backtest appears.
