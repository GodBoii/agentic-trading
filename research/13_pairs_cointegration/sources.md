# Primary sources inspected on 2026-10-01

| Source | What it establishes | Use here |
|---|---|---|
| [Gatev, Goetzmann and Rouwenhorst, Yale paper](https://repec.som.yale.edu/icfpub/publications/2573.pdf) | A daily normalized-price distance method on a long US history, with pair formation separated from trading. | Motivates relative-value research. This fixed Indian pair and minute data do not reproduce its universe, formation period, or empirical returns. |
| [Avellaneda and Lee, NYU author paper](https://math.nyu.edu/inmemoriam/avellaneda/AvellanedaLeeStatArb20090616.pdf) | Factor-residual statistical arbitrage, mean-reversion modeling, and variation through market regimes. | Motivates inspecting residual dynamics before trading a fitted relationship. Our single fixed pair is not their PCA/ETF multi-stock portfolio. |
| [statsmodels cointegration documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html) | Augmented Engle-Granger testing assumes I(1) input series and has a no-cointegration null. | Defines a future formal test. The package is absent, so no formal cointegration statistic, p-value, or significance claim is generated. |
| [statsmodels maintained repository](https://github.com/statsmodels/statsmodels) | Official implementation and econometric test infrastructure. | Future reference implementation. No external scripts executed and no package installation was required. |

High price correlation, fitted regression, and an AR1 coefficient below one are not substitutes for demonstrating stable cointegration, executable convergence, and net profit.
