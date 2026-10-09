# Causal variance forecast research

This study compares fixed EWMA forecasts with a rolling second-moment baseline on next-minute squared log midpoint returns. It asks about risk estimation, not direction, fills or profitability. No account simulation or trades occur.

## Sources

- [RiskMetrics technical document, fourth edition, December 1996, official MSCI archive](https://www.msci.com/documents/10199/5915b101-4206-4ba0-aee2-3449d5c7e95a). The indexed official document excerpt specifies decay 0.94 for daily horizons and 0.97 for monthly horizons. Direct PDF requests timed out twice, so this study does not claim a full document review. Applying both decays to minute observations is our frozen sensitivity adaptation, not an original RiskMetrics intraday calibration.
- [Patton, volatility forecast comparison using imperfect volatility proxies, 2011, author's PDF](https://public.econ.duke.edu/~ap172/Patton_vol_proxies_JoE_2011.pdf). Reviewed its conditional-variance and noisy-proxy discussion. Squared returns proxy conditional variance under a zero conditional-mean assumption. MSE and QLIKE address forecast evaluation, but their interpretation depends on measurement assumptions. Downsampled receipt midpoint returns with unverified quote ages are not proven unbiased latent-variance proxies.

## Formulas and timing

Return r_t is log of the current completed minute midpoint close minus log of the previous completed close. With zero conditional mean, the target proxy is r_t squared. EWMA updates next variance as lambda times previous variance plus one minus lambda times the just-completed squared return. Lambdas are 0.94 and 0.97. The rolling baseline averages thirty completed squared returns. All three start after thirty contiguous returns and share the first thirty-return mean as their seed.

Forecasts are assigned to the exact minute boundary using only receipts strictly before that boundary. The future minute's observations never enter its forecast. Offline grouping assumes a local timer could finalize observed minute closes at that boundary; this study measures no timer or pipeline processing latency. Outcomes become available at the following minute boundary. A session's last partial bar is excluded.

Each minute requires usable quality under the selected mode, first and last receipt within fifteen seconds of the boundaries, and no longer receipt gap. Missing or invalid minutes reset all history and pending predictions. Models reset each session, and stocks have separate state. Predictions and outcomes use identical eligible pairs across all models.

MSE is the squared difference between forecast variance and observed squared return, in decimal log-return fourth-power units. Gaussian QLIKE is log of forecast variance plus observed squared return divided by forecast variance. A fixed positive forecast floor of 1e-12 keeps zero-variance predictions finite. Zero realized returns remain zero; we do not floor targets. QLIKE values can be negative in these units. Lower is better, and for positive outcomes this form differs from the ratio-based nonnegative form only by an outcome-specific additive constant.

## Reproduce

Run `python -m unittest discover -s research/18_volatility_forecasts/tests -v`, then `python -m research.18_volatility_forecasts.run` from the repository root. Frozen hypotheses are in `hypotheses.md`. Runs retain source snapshots, tape manifests, per-pair forecasts/outcomes, quality counts and aggregate losses. Existing run directories cannot be overwritten.

Seven historical days were inspected earlier in this project. Receipt-proxy results do not verify source quote age. Forecast accuracy is not directional alpha, and selecting the best loss on these days is not enough to choose a live risk model. Future validation should use new timing-verified sessions and explicit calibration tests before using forecasts to change position sizes or stops.
