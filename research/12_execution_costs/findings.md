# Initial findings, 2026-10-01

Execution conservatism does not rescue the fixed momentum policy. All three receipt-proxy scenarios lose in all seven sessions. The separate no-trade control creates no orders, fees, or P&L in either mode.

| Scenario | Strict trades | Strict net Rs | Proxy trades | Proxy gross Rs | Proxy fees Rs | Proxy net Rs |
|---|---:|---:|---:|---:|---:|---:|
| Base, 250 ms and 1 bps/leg | 2 | -905.93 | 155 | -5,944.02 | 11,698.51 | -17,642.53 |
| 1% aggregate footprint | 1 | -16.53 | 359 | -3,851.47 | 12,958.60 | -16,810.07 |
| Joint 3-second and 3 bps/leg stress | 1 | -302.82 | 116 | -9,043.05 | 8,778.14 | -17,821.19 |
| No-trade control | 0 | 0 | 0 | 0 | 0 | 0 |

The smaller footprint creates more than twice as many trades. Smaller positions take longer to reach the monetary daily loss threshold, so subsequent entry opportunities differ. Its smaller total loss cannot be interpreted as improved alpha. It spends more absolute fees despite smaller orders. Joint delay/slippage stress admits fewer trades and worsens gross losses. It cannot isolate latency from slippage.

Mean individual-trade net returns are -14.18 bps for base, -14.45 bps for the 1% footprint, and -18.70 bps for joint stress. Mean individual-trade fee burdens are 8.74, 9.92, and 8.71 bps respectively. Average entry notional falls from Rs88,559 to Rs38,334 under the footprint restriction. These unweighted trade averages are descriptive, not independent estimates or account returns.

The base's actual simulated entry wait averages 1,637 ms despite its configured 250 ms delay. The joint stress waits average 3,837 ms. Both must wait for a later recorded observation. These are replay sampling and order-arrival effects, not observed broker latency.

The base reproduces the earlier lab's 155-trade receipt-proxy momentum result to the reported precision. All 56 policy/session runs complete without unresolved exposure. Five explicit behavior tests pass, covering later-observation execution, entry and exit latency, long/short fee accounting, restrictive footprint sizing, fixed-flat-quote slippage direction, and no-trade accounting. Source snapshots and trade manifests stay in `runs/initial-v1`.

## Fee size sensitivity

For a hypothetical flat Rs100 entry and exit price, the frozen fee model gives the following round-trip fees before spread and slippage. These values are model checks rather than account-specific tariffs.

| Entry notional Rs | Model fee Rs | Fee bps |
|---|---:|---:|
| 5,000 | 4.92 | 9.84 |
| 20,000 | 21.64 | 10.82 |
| 100,000 | 82.68 | 8.27 |
| 500,000 | 224.60 | 4.49 |

The capped brokerage component changes effective fees with order size. Independent per-order rounding can also make small-size fee rates non-monotonic. Actual contract-note aggregation and rounding need reconciliation before relying on these figures. A strategy with a ten-basis-point gross target can still lose after a small spread and two slippage legs.

## What remains unresolved

The tape lacks the per-level sizes and event sequences needed to walk the book or estimate passive queue fills. Neither 1% nor 10% of five-level aggregate quantity proves availability at the best quote. The 250 ms scenario is constrained by later sampled observations rather than a calibrated subsecond route. These stress outcomes are historical sensitivity evidence with unverified quote age, not measurements of broker latency or market impact.

Keep the fixed momentum policy as a negative control. Future execution research needs per-level books, source quote timestamps, submission/acknowledgement/fill/cancel timestamps, partial fills, and rejected-order reasons. Fit latency and cost distributions on calibration data, then freeze them before strategy evaluation. The [hftbacktest maintainer documentation](https://hftbacktest.readthedocs.io/en/latest/order_fill.html) explains why even full-book replay cannot create actual market impact; the [Dhan pricing page](https://dhan.co/pricing/) remains the tariff reference for reconciliation.
