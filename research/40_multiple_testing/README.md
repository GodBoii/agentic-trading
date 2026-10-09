# Multiple-hypothesis research audit

Testing many ideas can create apparent winners without a durable advantage. We keep unsuccessful variants, split dates chronologically, and count comparisons instead of reporting only the maximum.

Sources reviewed include [Bailey and coauthors on backtest overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), the [authors' overfitting discussion](https://www.davidhbailey.com/dhbpapers/overfitting.pdf), and the official [statsmodels multiple-testing implementation](https://github.com/statsmodels/statsmodels/blob/main/statsmodels/stats/multitest.py). The documented Benjamini-Hochberg method adjusts a family of valid pvalues under suitable dependence assumptions. It does not fix bad prices, missing fills, or reuse of evaluation data.

This folder implements an exact session sign-flip tail and BH adjustment as diagnostics on completed validation comparisons. The exact tail requires independent symmetric null errors. Those assumptions are not established for these financial recordings. Therefore the output numbers cannot be treated as calibrated strategy significance or a deployable discovery.

There are only two validation dates. At most four sign permutations are available, so even two positive nonzero dates cannot yield a raw one-sided tail below0.25 with this diagnostic. More strategies do not create more independent dates. Incomplete validation exposure is excluded instead of treating closed trades as total P&L. Zero-trade strategies remain visible and cannot become a positive discovery.

Run `python -m research.40_multiple_testing.run` after all track batches finish. Completed versions remain separate. No profitable version selection or parameter fitting takes place here.
