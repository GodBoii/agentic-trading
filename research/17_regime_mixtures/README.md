# Frozen regime mixtures

This track tests whether a two-component feature-density model can condition a continuation rule and a fade rule. The model fits observations, not profits. A high component responsibility means a feature vector resembles that fitted component under Gaussian assumptions. It is not a probability of winning a trade.

Run `python -m research.17_regime_mixtures.run` from the repository root. Run behavior tests with `python -m unittest discover -s research/17_regime_mixtures/tests -v`. Fitted model files and run evidence refuse overwrite.

## Sources and model choice

- [statsmodels official MarkovRegression documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.regime_switching.markov_regression.MarkovRegression.html) distinguishes regime-specific distributions and transitions. [The filter method](https://www.statsmodels.org/stable/generated/statsmodels.tsa.regime_switching.markov_regression.MarkovRegression.filter.html) applies a Hamilton filter; smoothing is a separate operation. This experiment uses a simpler independent Gaussian mixture with no learned transition process. It does not implement MarkovRegression or infer future-smoothed states.
- [scikit-learn official Gaussian-mixture guide](https://scikit-learn.org/stable/modules/mixture.html) describes Gaussian density components, expectation-maximization and covariance choices. [GaussianMixture API](https://scikit-learn.org/stable/modules/generated/sklearn.mixture.GaussianMixture.html) documents diagonal covariance and component responsibilities. The locally written NumPy implementation uses that mathematical model, not scikit-learn code. No new package was installed or external executable downloaded.

## Causal features

Collect six completed one-minute midpoint bars. Each bar requires at least ten observed quotes, observations within ten seconds of both minute edges, and no unusable quote or gap over fifteen seconds. Features release only after the next minute starts. For the five close increments `r[j] = 10000 * ln(close[j+1] / close[j])`, define:

- Return as `sum(r[j])`, in bps.
- Volatility as the population standard deviation of those five increments, in bps.
- Path efficiency as `abs(sum(r[j])) / sum(abs(r[j]))`, or zero for a flat path.

Overlapping five-minute windows and correlated stocks mean feature rows are not independent samples. Quote count is not volume. No forward-filled observations become training samples.

## Frozen fitting

Use only August 19, 20 and 21, with the fixed prior-August 18 top-12 ADV universe. Require at least 200 feature rows total and twenty from each day. Strict and receipt-proxy models train separately. Insufficient strict observations produce no fit and no trades.

Fit mean and population standard deviation normalization on training features. A feature scale below `1e-6` refuses the fit. Use two diagonal Gaussian components. Initialize one mean from each efficiency-sorted half, with NumPy generator seed 17. Initial variance is one and weights are equal. Run exactly thirty EM iterations, with normalized variance floor 0.01. A component effective mass below one refuses the fit. No restarts, component-number search or validation selection occurs.

For normalized feature `z`, component log density is `log(weight[k]) - 0.5 * sum(log(2*pi*variance[k]) + (z-mean[k])**2 / variance[k])`. Responsibilities normalize exponentials after subtracting the maximum log density. EM updates weights, weighted means and weighted diagonal variances. Save the full training likelihood trajectory, normalization and parameters. Label the component with higher fitted path efficiency as the trend component. The other component is low efficiency, not a proven mean-reverting process.

## Two frozen trading rules

| Rule | Admission |
| --- | --- |
| Trend continuation | Require trend-component responsibility at least 0.8, five-minute move magnitude 15 to 100 bps and latest completed-minute movement of at least 1 bps in the move direction. |
| Low-efficiency fade | Require the other component's responsibility at least 0.8 and the same move range, then a latest completed-minute turn of at least 1 bps opposite the five-minute move. |

Evaluate August 24, 25, 31 and September 1 without refitting normalization, mixture or thresholds. Model files and replay plan include training data hashes. Use common fees/account/fill controls with a 30 bps target, 20 bps stop, 600-second horizon and cooldown, 5 bps maximum spread and cost-room gate.

Component labels describe historical feature densities and can change meaning across markets. Their fit provides no causal explanation for future returns. Receipt-proxy freshness is explicitly unverified, source quote age is absent, all dates were previously observed, and every result has live promotion disabled.
