# Option structures and hedging, 1 October 2026

All 36 unconditional entry configurations lost money after estimated costs on their priced trades. The experiment contains 7,199 priced trade records and 328 unresolved exits across thirteen dates with priced options. The same market intervals appear in many configurations, so those 7,199 records are not independent trades or one account's combined P&L.

This is a useful rejection of the idea that repeatedly opening a familiar structure creates income by itself. It does not reject selective option trading, volatility forecasting, different holding periods, or event-specific policies. Those questions need their own protocols and new validation data.

## Exact protocol

At each available complete minute close, the fixed policy attempts its specified structure. It uses the nearest currently quoted strike to the futures price as an ATM proxy. The earliest currently available option expiry is selected. Ties use the lower strike. There is no directional signal, IV condition or retrospective leg optimisation.

Candidates require contemporaneous backward-only quotes no older than two seconds by receipt time. Identities are chosen at decision time and frozen. Entry uses the same contracts one second later. Buys pay ask and sells receive bid. Liquidation reverses those sides at the fixed five-, fifteen- or thirty-minute horizon. There is one 65-unit lot per leg. Strike spacing is fixed at fifty points. An iron condor sells the nearest OTM put and call and buys the next strike on each side. An iron butterfly sells ATM put and call and buys the adjacent wings.

Each policy has one conditional position open at a time. Entries whose planned exits cross the known normal-session close are blocked. The policy never reads future quote coverage or forward return labels to decide entry. If an exit cannot be valued, its contracts remain in the ledger and that policy halts for the rest of that date. The unknown liability is not set to zero.

Hypothetical liquidation marks every thirty seconds estimate a sampled adverse excursion including roundtrip costs. Missing marks remain recorded. These values can understate true intratrade losses, especially during gaps. They are not continuous maximum-loss observations. An unresolved exit may hide a worse subsequent outcome.

The cost model includes per-order brokerage, premium-based option-sale STT, exchange/IPFT estimate, SEBI levy, buy stamp duty, applicable GST and 0.10 premium points of extra slippage per leg per transaction. A second scenario raises that slippage to 0.50 points. The configuration JSON preserves exact rates. Atomic fills, market impact, queue priority and quote capacity are unavailable.

## What happened

Representative configurations are below. The full 36-row table is in [artifacts/table.md](artifacts/table.md).

| Structure | Hold min | Priced trades | Unknown exits | Net INR, priced only | Worst sampled adverse P&L INR |
|---|---:|---:|---:|---:|---:|
| Long call | 5 | 422 | 10 | -35,670 | -994 |
| Long put | 5 | 429 | 10 | -37,874 | -2,179 |
| Short straddle | 15 | 158 | 10 | -23,666 | -4,225 |
| Short strangle | 30 | 74 | 8 | -7,559 | -3,060 |
| Bull call spread | 15 | 156 | 10 | -24,691 | -675 |
| Bear put spread | 15 | 144 | 10 | -23,520 | -665 |
| Iron condor | 15 | 83 | 6 | -25,798 | -2,350 |
| Iron butterfly | 15 | 142 | 10 | -46,832 | -1,368 |

Long and short versions both lose under the unconditional entry protocol. Spreads, brokerage and taxes consume the small changes available during many short holding periods. Comparing each structure's aggregate P&L directly would be misleading because requiring extra legs changes entry availability and the nonoverlapping schedule.

The paired comparison therefore keeps only identical entry times and reports unresolved pairs separately. At fifteen minutes there were 116 common short-straddle/iron-butterfly entries. Of these, 107 pairs were priced and nine pairs had an unknown valuation. On the priced pairs, the worst sampled adverse P&L was INR -4,225 for the short straddle and INR -1,368 for the butterfly. Adding wings also added about INR 139 in estimated roundtrip costs per pair and reduced net P&L by INR 19,243 across those pairs. The observed protection costs money. It does not demonstrate that the butterfly is preferable on return on capital, because margin and available capital are absent.

The fifteen-minute strangle/condor comparison had 42 priced common entries and four unresolved pairs. Worst sampled adverse P&L was INR -3,277 versus INR -2,350. The condor added about INR 134 in estimated roundtrip costs and reduced paired net P&L by INR 10,323. These small, incomplete samples say little about rare tail events.

## Formulas and what they establish

For leg side q equal to +1 for a long and -1 for a short, executable quoted mark-to-market before explicit fees is:

\[
P\&L_t = 65\sum_i q_i\left(p_{i,t}^{close}-p_i^{entry}\right).
\]

Entry is ask for a long and bid for a short. Closing price is bid for a long and ask for a short. Net P&L subtracts transaction costs for both directions. A midpoint payoff does not represent the same experiment.

An equal-width iron condor receiving c premium points has maximum terminal profit 65c and maximum terminal loss 65 times width minus c, before costs. A butterfly uses the same formula for its single-wing width. Those limits assume all intended legs exist and are held through expiry. They do not bound temporary losses from missing hedges or give the broker's required margin. The payoff definitions follow the [OIC guide](https://www.optionseducation.org/getmedia/68305977-b772-41c8-bf1d-3d405725b3cf/options-strategies-quick-guide-2025.pdf).

An approximate delta-hedged short-option increment under smooth movement is:

\[
\Delta P\&L \approx -\tfrac12\Gamma\left[(\Delta S)^2-\sigma_{IV}^2S^2\Delta t\right]-\text{hedge costs},
\]

with additional vega, skew, rates, jump and basis effects when their assumptions fail. This explains why premium selling depends on realised movement relative to priced volatility and execution costs. It is not a trading signal by itself.

## Synthetic delta hedging

The archive lacks synchronised spot, validated option Greeks, an IV surface, futures hedge size information and historical margin. I therefore did not claim an empirical delta-hedged strategy backtest. The separately stored simulation uses 2,000 fixed-seed GBM paths, known 20% volatility, zero rates, initial underlying 24,000, one trading-day maturity and fractional generic underlying units. Initial ATM call premium is 120.63 points.

The seller receives the model premium, buys the model delta, funds every subsequent hedge through a cash account, pays each modelled transaction cost, pays the terminal option payoff and unwinds the hedge. The structure follows the question studied by [Derman and Kamal](https://emanuelderman.com/wp-content/uploads/1998/12/risk-non_continuous_hedge.pdf) and the primary [QuantLib discrete-hedging example](https://github.com/lballabio/QuantLib/blob/master/Examples/DiscreteHedging/DiscreteHedging.cpp). This is an independent simplified implementation, not a run of either repository.

| Rebalance min | No-cost P&L standard deviation, points | Mean hedge cost at 5 bp each side, points | Mean P&L at 5 bp each side, points |
|---|---:|---:|---:|
| 1 | 5.39 | 87.96 | -87.78 |
| 5 | 12.25 | 45.68 | -45.20 |
| 15 | 20.22 | 31.01 | -30.24 |
| 30 | 27.56 | 25.10 | -24.63 |
| 60 | 36.52 | 21.47 | -20.13 |

Faster hedging reduces replication-error dispersion in this model. It also increases turnover costs. The generic 5 bp each-side scenario is not the Indian futures cost schedule. It is a sensitivity parameter. Fractional generic underlying hedges differ materially from integer Nifty futures lots, basis risk and broker margin.

There are fifteen synthetic frequency/cost configurations, separate from the 36 empirical quote-replay configurations. No setting is promoted as optimal. The [Deep Hedging paper](https://arxiv.org/abs/1802.03042) and [author repository](https://github.com/hansbuehler/deephedging) motivate a later constrained, risk-sensitive optimisation, but no neural hedge is trained or validated here.

## Verification and next questions

Nine focused tests pass. They exercise backward-only freshness, rejection of contract changes and crossed quotes, one-second repricing, fixed contract identities, unpriced-position halts, condor terminal bounds, closing-spread costs, deterministic strike choice, known session-close limits and the effect of costs on identical synthetic paths.

The useful next questions are selective entry based on priced volatility, hedges at different distances, cost-aware minimum holding periods and whole-position exit policies. Each should retain the current identity, freshness and unknown-exposure rules. More expiry sessions, long dated options and fresh untouched dates are needed before selecting a strategy from these results. Short-option margin remains unavailable in every saved result.
