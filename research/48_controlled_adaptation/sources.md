# Motivation and scope

Primary sources checked on 2026-10-09.

- [DoubleAdapt original paper, arXiv 2306.09862](https://arxiv.org/abs/2306.09862), Lifan Zhao, Shuming Kong and Yanyan Shen. Published at KDD 2023; arXiv revision 2024-04-07. Its contribution is learning data and model adapters through meta-learning to address changing stock-data distributions.
- [Official DoubleAdapt repository](https://github.com/SJTU-DMTai/DoubleAdapt). The authors describe delayed labels explicitly and recommend update spacing greater than the target horizon. They also distinguish adaptation of data from adaptation of forecast-model parameters.
- [Official implementation, src/model.py](https://raw.githubusercontent.com/SJTU-DMTai/DoubleAdapt/main/src/model.py), reviewed directly. `IncrementalManager` updates on supplied training tasks and evaluates on separate test task indices. `DoubleAdaptManager` adds learned feature/label adaptation and a differentiable inner optimization context. We used this source to verify what a full implementation would require, not to execute it.

This experiment borrows the question of whether adaptation helps under drift. It does not implement the paper's data adapters, model adapters, meta-gradients, neural forecast model or Chinese equity evaluation. None of its figures are a DoubleAdapt reproduction. No remote repository code was installed or run.

The tested formulas are deliberately narrower. Weighted ridge minimizes `sum_i w_i(y_i-b-x_i beta)^2 + alpha*||beta||^2` after training-weighted feature standardization. The intercept is unpenalized. Static fitting uses 2022-2023. Expanding monthly fitting adds only matured earlier labels. Rolling fitting keeps a 12-calendar-month history. Recency weighting sets `w_i = 2^(-trading_date_age_i/90)` and normalizes average weight to one.

The controlled selector tests actual, immutable incumbent coefficients against challenger shadow models using a past validation block. It refuses comparisons if any incumbent training label overlaps that block. A successful shadow fit is refit with matured history before deployment, and both hashes are logged. This is controlled offline updating, not a live learning system.
