# Execution economics and assumptions

Keep the original causal momentum policy fixed. Change three execution scenarios, then compare an explicit no-trade accounting control.

| Scenario | Order latency | Extra slippage per leg | Aggregate displayed depth limit |
|---|---:|---:|---:|
| Base | 250 ms | 1 bps | 10% |
| Restrictive footprint | 250 ms | 1 bps | 1% |
| Joint stress | 3,000 ms | 3 bps | 10% |
| No-trade control | No orders | No orders | No orders |

The joint scenario cannot identify separate latency and slippage effects. More conservative entry assumptions can reduce activity, delay the daily loss halt, change the set of later trades, and sometimes produce a smaller total loss. That does not mean worse execution improves expected alpha. Compare per-trade economics and censored trade paths before interpreting aggregate differences.

Footprint uses five-level aggregate displayed quantity, not best-quote quantity. Even 1% does not establish fill capacity, queue position, or absence of impact. The one-second tape also prevents subsecond latency calibration. A 250 ms configured delay often waits for a later one-second observation. Broker API rate limits provide no exchange-to-fill latency guarantee.

The shared fee model rounds each order independently and needs real contract-note reconciliation. Spread is already included in bid/ask fill prices. Slippage is added separately, and fees use each executed leg. Every daily scenario begins from the same illustrative account; totals do not compound or estimate annual returns.

Run `python -m research.12_execution_costs.run` from the repo root for fresh evidence. The fixed run name refuses to overwrite existing artifacts. Run tests with `python -m unittest discover -s research/12_execution_costs/tests -v`. The five tests verify long/short accounting, later fills, entry and exit delay, footprint sizing, slippage direction on fixed flat quotes, and the no-trade control.
