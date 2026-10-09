# Dependence and search-selection study

This study re-examines previously viewed baseline predictions. No new market evidence is created.

| Added features | Minute-IID interval | Date interval | Nonoverlap date interval | Family p |
|---|---|---|---|---:|
| price_near_depth | -0.061 to 0.271 | -0.334 to 0.488 | -0.596 to 0.365 | 0.477 |
| price_all_depth | -0.624 to -0.064 | -1.185 to 0.647 | -1.734 to 0.455 | 0.645 |
| price_depth_estimated_flow | -0.578 to -0.008 | -1.127 to 0.810 | -1.683 to 0.768 | 0.568 |

Improvement is price-model MSE minus candidate MSE, in bps squared. Positive favours added features. Minute-weighted and equal-date estimands differ; they must not be described as identical confidence intervals. Day sign randomisation uses one common sign per date across models. It requires date-level symmetry and independence. It is an exploratory max-statistic correction for three models, not a complete White Reality Check or PBO estimate.

## Synthetic search

| Candidates searched | Selected training mean | Fresh mean |
|---:|---:|---:|
| 1 | -0.004 | 0.003 |
| 10 | 0.512 | 0.002 |
| 40 | 0.723 | 0.001 |
| 100 | 0.833 | 0.002 |

Synthetic returns are independent standard-normal observations, not Nifty data or INR returns. The example shows why choosing the best of forty backtests can produce an attractive training number under a zero-edge null.

## Sources

[Bailey et al., backtest overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659)

[Politis and Romano's stationary bootstrap](https://doi.org/10.1080/01621459.1994.10476870)

[ARCH resampling implementation](https://github.com/bashtage/arch/tree/main/arch/bootstrap)

[Statsmodels multiple-testing methods](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)

Methods implemented locally and tested. Public repos were inspected as sources rather than downloaded and executed.

Run `python research/06_dependence_and_selection/study.py` from nifty-research.
