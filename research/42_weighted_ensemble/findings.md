# Findings from initial-v1

Combining these inputs did not establish a trading edge. The learned blend
slightly reduced net-return forecast error, almost entirely matching the spread
specialist. It had worse preferred-side accuracy than a fixed always-long
control. Every variant abstained at the frozen 2 bp predicted-net-return gate.

The experiment ran 56 account replays across seven variants, two freshness modes
and four evaluation sessions. All completed with no unresolved exposure, no
trades and Rs 0 P&L. Zero P&L is an abstention result, not a profitable strategy.
The existing verifier passed source/input hashes, coverage and accounting.
Nine focused tests passed before model fitting.

Receipt-proxy evaluation produced 12,248 rows with complete future executable
labels from 537,398 shared tape observations. The causal account policies made
13,233 forecast decisions each; additional decisions lacked acceptable future
label intervals. Neither prediction nor replay used those future intervals as
an admission filter. Forecast statistics below necessarily use complete-label
rows. All seven variants use the same rows.

| Predictor | Net-return RMSE, bps | Preferred-side accuracy | Account trades |
| --- | ---: | ---: | ---: |
| Constant base-training mean | 6.783875 | See fixed-side controls below | Not a replay variant |
| Momentum specialist | 6.795362 | 47.31% | 0 |
| VWAP specialist | 6.790890 | 47.26% | 0 |
| Depth specialist | 6.782426 | 51.40% | 0 |
| Spread specialist | 6.745230 | 46.24% | 0 |
| Joint ridge | 6.760381 | 50.60% | 0 |
| Equal average | 6.762871 | 47.31% | 0 |
| Learned convex average | 6.745060 | 46.24% | 0 |

Preferred-side accuracy means choosing the side with the higher realized
executable net-return label. Both choices can lose after costs. It is not
profitable-trade accuracy or an exact raw-price direction metric. Always choosing
long matched the preferred label 53.76% of the time; always choosing short did so
46.24% of the time. The learned blend matched the always-short control's
aggregate accuracy. Only 2.49% of its selected hypothetical labels were positive,
before the account gate, while its average selected label was -12.23 bps.
No prediction met the model's required predicted net edge, so these are
prediction diagnostics rather than executed trades.

Base specialists and normalization used 7,343 rows from August 19-20 only.
Weights used 3,940 August 21 rows from those frozen models, with no base-model
refit. The learned weights were momentum 0%, VWAP 0%, depth 14.33% and spread
85.67%. The spread model mainly predicts costs. A larger weight therefore does
not demonstrate stronger directional prediction.

The learned blend's pooled RMSE was only 0.000170 bps below the best single
specialist. It beat spread RMSE on two evaluation sessions and lost on two.
Specialist residual correlations ranged from 0.989 to 0.999. These predictors
largely shared their errors, leaving little useful diversification in this
comparison. These four-day descriptive differences do not justify a significance
claim or model promotion.

| Session | Complete-label rows | Spread RMSE, bps | Learned blend RMSE, bps |
| --- | ---: | ---: | ---: |
| 2026-08-24 | 2,887 | 5.206968 | 5.206971 |
| 2026-08-25 | 2,980 | 6.227475 | 6.229090 |
| 2026-08-31 | 3,178 | 6.522521 | 6.521371 |
| 2026-09-01 | 3,203 | 8.441012 | 8.440265 |

Strict `recent_trade` had no base-training labels and only six weight-training
labels. The model correctly remained unfitted. It had 31 complete future labels
across the evaluation sessions, which cannot rescue missing training data.
All strict replays abstained. Receipt-proxy models permit unknown freshness and
do not establish source quote age. The cached universe and these historical
sessions were used by earlier research, so neither mode has a pristine holdout.

The result answers a narrow question. A convex blend of these four simple
specialists did not make this 60-second cost-adjusted forecast useful for
trading. It does not rule out other horizons, models, new independent sessions,
or genuine additional information. No thresholds were reduced after seeing the
abstention result, and no live orders were placed.

Evidence is in `runs/initial-v1/forecast-diagnostics.json`, `comparison.csv`,
`aggregate.json`, individual account summaries, `evidence-verification.json`
and the frozen training report in `models/initial-v1/frozen-models.json`.
