# Frozen numerical predictive models

This track compares fixed ridge and logistic numerical models without conversational agents. The five causal inputs are 15-second and 60-second midpoint returns, midpoint distance from current VWAP, five-level aggregate depth imbalance, and spread.

For each sampled decision, the label enters at a later same-instrument observation after at least 250 ms. It exits at the first observation at least 60 seconds after entry. Long uses ask then bid; short uses bid then ask. Both legs include 1 bps hypothetical slippage and the shared frozen fee model. Each label uses approximately Rs100,000 notional. Invalid observations or gaps within the entire label interval reject the row. Actual replay order quantities can be smaller, so label costs are an approximation and can understate their fee burden.

Features sample once per instrument per minute after continuous history. Labels stay within each session. Model training is restricted to Aug19, Aug20, and Aug21. Evaluation uses Aug24, Aug25, Aug31, and Sep1. These are historical diagnostics, and the last two were already inspected previously. They are not a pristine holdout.

Ridge minimizes average squared net-return error with 0.01 L2 coefficient penalty and an unpenalized intercept. A fixed 400-step deterministic logistic optimizer fits whether each side's label has positive net return. Means and standard deviations come only from training inputs. Arrays are frozen before evaluation. Less than 100 admitted training rows produces no model and no trades.

Three policy hypotheses test ridge predicted net return above 2 bps, the same ridge gate plus a 65% profit probability, and ridge predicted net return above 5 bps. These are fixed thresholds. Choosing the largest diagnostic P&L after this comparison does not validate it.

The replay horizon matches the 60-second training label, but the common engine can exit earlier at the shared stop or target. This mismatch must be considered when interpreting forecasts. Models estimate average fixed-horizon net return; they do not estimate path-dependent stop or target returns. Minute samples and cross-instrument dependence also prevent row counts from being treated as independent trials.

Run tests from the repo root with `python -m unittest discover -s research/08_statistical_models/tests -v`. See [sources.md](C:/Users/prajw/Downloads/Trader/research/08_statistical_models/sources.md), [findings.md](C:/Users/prajw/Downloads/Trader/research/08_statistical_models/findings.md), and the frozen model files created by the run.
