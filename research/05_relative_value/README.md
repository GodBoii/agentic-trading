# Cross-sectional relative movement

This track tests whether a stock's recent midpoint return relative to an equal-weight peer basket continues or reverses. It is a directional residual proxy. It does not place a basket hedge, estimate cointegration, or reproduce a market-neutral pairs strategy.

[Heston, Korajczyk and Sadka](https://arxiv.org/abs/1005.3535) study intraday cross-sectional patterns, including continuation at matching time-of-day intervals across days and short-term reversal associated with liquidity. Our five-minute residual experiment is an adaptation inspired by the continuation/reversal distinction. It cannot reproduce their multi-day seasonality design on seven selected sessions.

The reviewed [PairsTrading repository](https://github.com/akhil2706/PairsTrading) uses cointegration, OU spread calibration, formation and trading periods. That is a different design. We did not execute its code or claim a faithful replication. Proper two-leg pricing, execution, and longer formation history are required before using its mechanism in this project.

Frozen experiments use prior-Aug18 top12 NSE instruments, a300-second midpoint return, at least four other instruments observed within15 seconds, equal peer weights, a10-bps residual threshold, and common account/fee assumptions. Variants test continuation, unconfirmed reversal, and reversal with a2-bps recent directional turn. Every observation and peer value must already be available at decision time. Future peers and stale peers are excluded.

Run `python -m research.05_relative_value.run` from the repository root. Strict and receipt-proxy modes are separate. The results are historical diagnostics, not proof of live returns. Thresholds were fixed before opening outputs; no return-maximizing pair or parameter selection is performed.
