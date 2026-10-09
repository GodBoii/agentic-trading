# Methods and primary sources

This study uses the installed scikit-learn 1.8.0 implementation. The exact runtime version and frozen source are saved with each run.

Ridge minimizes squared prediction error plus `alpha*sum(coef^2)`. Alpha is fixed at 100. Each feature's mean and standard deviation come from 2022-2023 training rows only, so the penalty does not depend on each raw feature's unit. See [the version-matched Ridge documentation](https://scikit-learn.org/1.8/modules/generated/sklearn.linear_model.Ridge.html).

Histogram gradient boosting fits an additive collection of trees to reduce squared-error loss. Binned feature values and shallow trees allow nonlinear interactions. The additive prediction is an initial constant plus the contributions of 100 trees, with each contribution already scaled by the configured learning rate. Depth 3, at most eight leaves, at least 100 samples per leaf and L2 regularization 10 constrain the fit. See [the version-matched HistGradientBoostingRegressor documentation](https://scikit-learn.org/1.8/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html). Automatic early stopping uses a sample split in this estimator, so this experiment explicitly disables it. This avoids a hidden shuffled validation split. All 100 iterations belong to the frozen specification.

Single momentum rules use the observed causal `ret5`, `ret15` or `ret30` score as a continuation heuristic. Its magnitude is not a learned expected future return. Each candidate asks the shared account engine to enter only when the score's magnitude exceeds decision-time estimated round-trip fees, two adverse-cost legs and a fixed net threshold. Rule threshold calibration occurs on validation account PnL only.

Nine frozen decision policies represent three families for each of three forecast horizons. The finite grid has 36 active validation trials, plus a zero-PnL no-trade comparator in each of nine selection groups. The maximum over the grid is a selected result. Test comparisons retain all nine selections, including abstention; they do not create a new test-selected policy.

Training, validation and test use whole IST session-date groups. Label intervals that cross a split boundary are purged. Within-day horizon labels can overlap; account replay handles overlapping trades and date-level dependence remains a limit on statistical inference. Each model forecasts the same rows for its horizon. The shared dataset retains rows with all three valid horizons, enabling horizon comparisons on the same decision cohort.
