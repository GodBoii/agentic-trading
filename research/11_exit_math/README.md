# Exit mathematics and holding-time research

This track tests whether fixed exit distance and maximum holding time materially change the economics of unchanged baseline momentum signals. It also checks the mathematics of required success rates and the difference between a stop trigger and its eventual fill.

## Sources reviewed

- [Leung and Zhang, optimal trading with a trailing stop](https://arxiv.org/pdf/1701.03960). Reviewed the diffusion formulation, path-dependent drawdown floor and associated acquisition/liquidation problem. Its optimal boundaries require an assumed process and calibrated parameters. A percentage stop is not universally optimal. This experiment does not implement the paper's differential-equation solution or trailing stop.
- [Leung and Li, mean reversion with transaction costs and a stop-loss exit](https://arxiv.org/pdf/1411.5062). Their model couples entry and exit decisions for a mean-reverting spread. Our single-stock momentum stream is a different process, so their analytical boundary cannot be copied into this engine without fitting and validating a spread model.
- [Kaminski and Lo, MIT repository manuscript record](https://dspace.mit.edu/entities/publication/bb69ca4b-0cdc-487f-831d-63b2e84fafee). Reviewed the repository abstract and metadata; the PDF download returned HTTP405. The abstract describes evaluating portfolio stop rules under daily futures data. We do not claim to reproduce that study or quote unread proofs.

These sources motivate asking how exit rules interact with a price process, trading costs and entry conditions. They do not provide a ready profitable NSE cash strategy.

## Analytical model

For two barrier outcomes with target gain T, stop loss S, success probability p and fixed round-trip cost C, all in basis points, expected net payoff is pT - (1-p)S - C. Break-even p is therefore the ratio of S+C to T+S. A thirty/fifteen gross payoff ratio needs one-third success without costs, but approximately 55.6% success if total cost is ten basis points. A gross two-to-one ratio alone says little about profitability.

This calculation excludes time exits, varying position sizes, variable costs, quote gaps, delayed execution and loss-action exits. It is a sanity check, not a predictor. The actual simulator retains these additional effects instead of forcing every trade into a win/loss barrier outcome.

## Experiments

Frozen comparisons use thirty/fifteen-basis-point exits over 300 seconds, constant doubled sixty/thirty distances over 300 seconds, and original distances over sixty seconds. The doubled distances are a fixed scale sensitivity, not dynamic ATR or volatility scaling. All use the original causal momentum policy.

Policy entry signals stay the same; filled entry sets need not. Wider stops change risk sizing and exits change available portfolio slots, cooldown clocks and account loss actions. The result is a whole-account strategy comparison, not isolated counterfactual P&L on a fixed trade list. Source code and complete parameters are frozen in each run.

## Reproduce and next work

Run `python -m unittest discover -s research/11_exit_math/tests -v` and `python -m research.11_exit_math.run` from the repository root. Saved tests cover break-even algebra, impossible cost hurdles, invalid parameters, delayed time exit, stop overshoot and later target fills.

After the account runs, `python -m research.11_exit_math.paired` freezes baseline receipt-proxy filled entry timestamps, prices and quantities, then compares all three exits on precisely those entries. It excludes portfolio loss actions and allows overlapping counterfactual positions. Its totals diagnose exits but cannot be traded as a feasible account. Incomplete future quotes remain unresolved. Plans preserve tape hashes, baseline journal hashes and a snapshot of the paired code.

Before fitting adaptive exits, capture timing-verified continuous data and compare predeclared regimes on new sessions. A paired exit-only counterfactual study should separately freeze entry timestamps and quantities, then account for positions that overlap and cannot coexist in one account. A more accurate execution model is needed before attributing small differences to optimal stopping.
