# Opening-range research

This track asks whether a complete NSE cash opening range contains usable continuation information after spread, simulated slippage, Indian cash fees, and account limits. Three hypotheses are frozen in [hypotheses.md](C:/Users/prajw/Downloads/Trader/research/02_opening_range/hypotheses.md). Code is an offline adaptation, not a faithful reproduction of a published profitability result.

## Sources reviewed

- [Zarattini, Barbon, and Aziz, first version February 2024](https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf). Their US study uses opening-range direction, prior daily liquidity/ATR filters, opening relative volume, and ATR-based stops. Its plain diversified ORB baseline underperforms its benchmark; high relative-volume selection is central to the stronger result. Our tape does not provide the fourteen preceding daily opening-volume histories needed for that selection. Our adaptation therefore cannot test the paper's main edge or transfer its claimed returns to NSE.
- [QuantConnect's official implementation discussion](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/). Reviewed its documented entry construction, relative-volume ranking, and risk logic. Its strategy requires a much broader stock universe and prior opening-volume measurements. We independently implement only opening-range and direction mechanics, rather than executing the linked code.
- [QuantConnect LEAN repository](https://github.com/QuantConnect/Lean). This is an engineering reference for a stateful backtester and indicator implementations. This track does not download or run LEAN.
- [Holmberg, Lonnback, and Lundstrom paper location](https://www.usbe.umu.se/digitalAssets/195/195397_ues948.pdf). Search returned paper metadata, but the PDF fetch failed. No claims or rules in our implementation depend on an unread paper.

## Method

Let H and L be the maximum and minimum received quote midpoints during 09:15 to 09:30 or 09:45 IST. Freeze these levels when the interval ends. Enter after a fresh usable observation exceeds H by at least the common confirmation buffer, or falls below L by that buffer. In the direction variant, the opening close must exceed the opening midpoint for a long and be below it for a short. In the VWAP variant, price must also be on the breakout side of supplied VWAP.

Only one signal per stock per session is emitted. No retry follows rejected execution. The entry window ends at 11:00. Each run creates a new policy for one day. A first receipt later than the allowed fifteen-second continuity gap after market open, an unusable opening receipt, a larger gap during formation, or missing closing range coverage invalidates the entire range. We never treat a late recorder start as a true opening range.

The range uses observed midpoints, not trade OHLC. Missing intra-second extremes remain unknown. Stops, targets and holding period come from the shared execution experiment and differ from the paper's ATR stop and end-of-day exit. Entry start is explicitly 09:30 for fifteen-minute variants and 09:45 for the thirty-minute variant. Default replay admission at 09:35 would incorrectly discard an earlier one-shot signal.

## Reproduce

From the repository root, run `python -m unittest discover -s research/02_opening_range/tests -v`, then `python research/02_opening_range/run.py` with the root on `PYTHONPATH`, or `python -m research.02_opening_range.run`.

The shared runner saves frozen parameters, manifests, session accounting, trade journals and aggregate comparisons under `runs/initial-v1`. Strict freshness is the default evidence gate. Receipt-proxy results are separate sensitivity experiments with unverified source quote age. They cannot establish deployable performance.

## What would count as progress

First establish complete opening capture and reliable source timing. Then add prior fourteen-session opening volume and daily ATR without selecting stocks from later outcomes. Compare the adapted baseline with a properly specified stocks-in-play mechanism on independent days. Seven already inspected diagnostic dates are too few to claim a trading edge.
