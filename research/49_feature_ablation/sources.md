# Method sources

This track tests independently specified feature additions, rather than reproducing a paper's performance. Primary references reviewed earlier in this research session support formulas, comparison discipline and nonlinear alternatives.

- [Qlib Alpha158 source](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/contrib/data/loader.py) provides candle, rolling price and volume factor examples. The local features are minute adaptations on the shared causal dataset. The full Alpha158 library was not trained here.
- [Gu, Kelly and Xiu's original article](https://academic.oup.com/rfs/article/33/5/2223/5758276) supports comparing disjoint chronological model samples and emphasizes momentum, liquidity and volatility inputs. Its original monthly US asset-pricing problem differs from these minute NSE stock targets.
- [scikit-learn Ridge documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html) specifies squared-error linear fitting with coefficient regularization. Installed sklearn version is recorded by the other model tracks. Fixed alpha100 is a hypothesis, not a proven optimal penalty.

Stock-minus-peer return and same-slot relative volume are local declared hypotheses. They do not establish market-neutral execution, institutional flow or causal news information. No absent index/sector/news data was synthesized.
