# Sources inspected on 2026-10-09

Microsoft Qlib source was inspected at commit
`54355232463878d2eebb91fe0ee5fa7fa1f5976c`, verified with `git ls-remote`.

- [Qlib AverageEnsemble source](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/model/ens/ensemble.py).
  The implementation standardizes model outputs within each datetime, then
  averages them. This track tests arithmetic averaging of forecasts already in
  the same net-bps units. It does not copy Qlib's cross-sectional normalization.
- [Qlib DoubleEnsemble source](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/contrib/model/double_ensemble.py).
  This implementation trains submodels, changes training sample weights, selects
  features from shuffled-feature error changes, and aggregates predictions using
  submodel weights. No Qlib model, sample reweighting or feature selection ran here.
- [Zhang et al., DoubleEnsemble](https://arxiv.org/abs/2010.01265).
  The authors study learning-trajectory sample reweighting and shuffled-feature
  selection for financial prediction. This is useful follow-up work once there
  are enough independent sessions. This track is a simpler constrained stacking
  experiment, not a replication of their reported stock-trading performance.
- [Blanc and Setzer, When to choose the simple average in forecast combination](https://www.sciencedirect.com/science/article/pii/S0148296316303952).
  The paper compares arithmetic averaging with learned combination weights and
  discusses estimation error and structural breaks. That motivates keeping the
  equal average as a mandatory control and learning weights on a separate
  chronological development session.

The custom convex objective is
`mean((sum_k w_k prediction_k - target)^2) + 0.1 sum_k (w_k - 0.25)^2`,
with `w_k >= 0` and `sum_k w_k = 1`. The four-dimensional quadratic is solved by
enumerating active simplex faces. The shrinkage strength is frozen, not chosen
after looking at evaluation results. No source claims this exact construction
has an established edge on these Indian equities.

Local track 08 contributes the causal feature collector and two-sided executable
labels. The dependency source and SHA-256 are saved alongside frozen models.
The common engine contributes account sizing, latency, charges and fill rules.
