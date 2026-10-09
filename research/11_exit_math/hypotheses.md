# Frozen exit hypotheses before runs

October 1, 2026. No tuning on this track's validation or audit outcomes.

- `fixed_30_15_300`: unchanged baseline momentum entries, target thirty basis points, stop fifteen basis points, maximum hold 300 seconds.
- `double_distances_60_30_300`: same raw entry policy, sixty-basis-point target and thirty-basis-point stop, same 300-second maximum hold. This is a constant doubled-distance stress. It is not ATR or dynamically volatility-scaled execution.
- `short_time_30_15_60`: same raw entry policy and thirty/fifteen barriers, maximum hold sixty seconds.

All account, cost, freshness, latency and other admission parameters remain shared defaults. The twelve-stock ADV universe is from August 18. Development dates are August 19, 20, 21; diagnostic validation August 24, 25; historical audit August 31 and September 1. All these sessions have prior project exposure.

The raw signal stream is identical because MomentumPolicy does not read exit thresholds. Admitted entries may differ because stop distance changes risk sizing and exits change slots, cooldown timing and loss-action history. Report those confounds rather than calling this a paired comparison of identical filled trades.

Run strict and receipt-proxy modes and retain every result. No neural model or optimal-stopping boundary is fitted. Any dynamic volatility model needs a future causal estimator, isolated execution implementation and independent data.
