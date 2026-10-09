# Sources inspected on 2026-10-01

| Primary source | What it supports | How this experiment uses it |
|---|---|---|
| [Gould and Bonart, queue imbalance](https://arxiv.org/abs/1512.03492) | Logistic relationships between best bid/ask queue imbalance and next midpoint movement on ten Nasdaq stocks. The strength differs between tick regimes. | Motivates imbalance hypotheses. Our five-level aggregate is a different feature, our horizon is longer, and we test executable P&L rather than transferring their accuracy claim. |
| [Cont, Kukanov and Stoikov, price impact of order book events](https://arxiv.org/abs/1011.6402) | Best-level event imbalance explains contemporaneous short-interval price changes, with depth-dependent impact. | Defines the data required for true OFI. Changes in our sampled aggregate totals cannot reconstruct their event measure. We explicitly label our measure snapshot depth change. |
| [Stoikov's microprice repository](https://github.com/sstoikov/microprice) | Author's fair-price estimator notebook and example data. | Establishes a future reproduction target. No repository scripts were executed. Our weighted quote uses aggregate depth and is not Stoikov's fitted microprice. |
| [Cont, Cucuringu and Zhang, cross-impact](https://arxiv.org/abs/2112.13213) | Integrated per-level OFI and lagged cross-asset OFI forecasting research. | Deferred. We lack per-level events and synchronized verified event time. |

The SSRN paper linked from Stoikov's repository returned HTTP 403. The repository README was inspected; the blocked full paper was not treated as read.
