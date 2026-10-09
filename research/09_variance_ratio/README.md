# Variance-ratio regime hypothesis

The descriptor is `VR(q) = sample variance of overlapping q-step return sums / (q × sample variance of one-step returns)`. Ratios above one are consistent with positive serial dependence, while ratios below one can describe reversal. Zero return variance produces an unavailable descriptor.

[Lo and MacKinlay's original paper](https://www.nber.org/papers/w2168) studies a specification test of random walks on weekly stock returns. Their [finite-sample investigation](https://www.nber.org/papers/t0066) matters because small samples can mislead. This intraday strategy adaptation uses a descriptor, not their formal test statistic or statistical rejection rule.

The reviewed official [arch VarianceRatio documentation](https://bashtage.github.io/arch/unitroot/generated/arch.unitroot.VarianceRatio.html) and [maintainer source](https://github.com/bashtage/arch/blob/main/arch/unitroot/unitroot.py) include debiasing and heteroskedasticity-robust inference. This small experiment does not implement those p-values, and its thresholds must not be interpreted as statistical significance.

Freeze31 completed minute midpoint closes to obtain30 log returns. Compare lag2 trend-following, lag2 adaptive direction, and lag5 adaptive direction. Trend requires VR>1.25. Adaptive reversal requires VR<0.75. The final five-minute completed-close move must exceed10 bps. Use only finalized quote minutes, reset state on data gaps, reject unknown strict freshness, and use shared cost/risk/fill controls.

Run `python -m research.09_variance_ratio.run`. Fine-grained source quote timing is unknown. The seven dates are previously inspected historical diagnostics; no pristine holdout or live edge is established.
