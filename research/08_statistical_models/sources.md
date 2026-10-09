# Sources inspected on 2026-10-01

| Primary source | What it supports | Decision for this research |
|---|---|---|
| [Gould and Bonart](https://arxiv.org/abs/1512.03492) | Queue imbalance with logistic prediction of next midpoint direction. | Logistic numerical baseline is worth testing. We predict probability of positive net executable return, a different and harder target. |
| [scikit-learn linear model source and documentation](https://github.com/scikit-learn/scikit-learn/blob/main/doc/modules/linear_model.rst) | Ridge penalized squared error and logistic probability models. | Implements these standard objectives with existing NumPy only. No downloaded code executes. |
| [TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | Ordered train/test splits avoid training on future observations; a gap can separate boundaries. | Whole-session training Aug19-21, then freeze all coefficients and evaluate later sessions. No labels cross session boundaries. |
| [DeepLOB paper](https://arxiv.org/abs/1808.03668) | Convolutional and recurrent models learn structured book sequences and achieve prediction results on benchmark and LSE data. | Neural implementation deferred. Current snapshots lack the per-level tensors and verified timing needed to reproduce this task. Prediction accuracy is not our net-return outcome. |
| [Author's DeepLOB implementation](https://github.com/zcakhaa/DeepLOB-Deep-Convolutional-Neural-Networks-for-Limit-Order-Books) | FI-2010 architecture notebooks in TensorFlow and PyTorch. | README inspected. No notebooks downloaded or executed. Keep this as a reproducibility target after collecting appropriate books. |
| [Author's multi-horizon implementation](https://github.com/zcakhaa/Multi-Horizon-Forecasting-for-Limit-Order-Books) | FI-2010 multi-horizon sequence forecasting and hardware acceleration reference. | Defers multi-horizon neural models until baseline economics and input fidelity are established. |

These papers and repositories motivate testable hypotheses. They do not validate execution, fees, or profitability in this Indian equity cohort.
