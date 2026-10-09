# Findings from the frozen sequence comparison

The actual GRU and MLP experiments did not establish improved prediction or a
profitable trading edge. Validation selected the equal average of three GRU
seeds by lowest raw-return RMSE. On the later evaluation period, that average
lost to zero-return persistence, the training-mean predictor and the fixed
training-majority direction control. Its primary candle-account simulation
also lost money.

This track used all 277,704 admitted shared rows. Training contained 119,238
rows from 485 sessions in 2022-2023. Validation contained 61,719 rows from 245
sessions in 2024. Evaluation contained 96,747 rows from 384 sessions in
2025-2026. These rows overlap in stocks, market conditions and some label
intervals. They are not 277,704 independent trials.

Thirty already completed minute bars provide five sequence channels, and all
models receive the same 21 causal context columns. The tabular MLP and ridge
also receive sequence mean, standard deviation, last value and sum per channel.
The forward GRU receives the ordered sequence. The raw return label uses an
entry open one full minute after decision availability and an exit open 15
minutes after entry. No same-observation fill or backward recurrent smoother
runs.

The MLP has 1,889 parameters. The GRU has 1,729. Three fixed seeds were trained
for each architecture. All feature normalization and target scaling used only
training rows. Validation MSE selected a checkpoint under the frozen patience
rule; all checkpoints, fitted scalers, ridge weights and the validation-only
selection record were saved before test predictions or metrics.

| Variant | Validation RMSE, bps | Evaluation RMSE, bps | Evaluation raw sign accuracy |
| --- | ---: | ---: | ---: |
| Training-mean constant | 38.78578 | 32.70363 | 51.80% |
| Zero-return persistence | 38.78793 | 32.70056 | No direction forecast |
| Summary ridge | 38.81028 | 32.73424 | 50.78% |
| MLP seed 17 | 38.82781 | 32.74508 | 50.22% |
| MLP seed 29 | 38.83696 | 32.73754 | 50.55% |
| MLP seed 43 | 38.80704 | 32.73714 | 51.15% |
| MLP equal seed average | 38.79580 | 32.71674 | 50.75% |
| GRU seed 17 | 38.77730 | 32.73603 | 51.01% |
| GRU seed 29 | 38.80703 | 32.74881 | 51.25% |
| GRU seed 43 | 38.78878 | 32.75505 | 50.37% |
| GRU equal seed average, selected on validation | 38.77312 | 32.73036 | 51.07% |

The selected GRU average improved validation RMSE by only 0.01266 bps over the
training-mean control. That descriptive difference did not persist in the
later period. The training-majority direction was short and matched 51.80% of
the 94,391 nonzero evaluation labels. The selected GRU average matched 51.07%.
Raw sign accuracy excludes zero target labels. A zero prediction has no
direction and is incorrect on nonzero targets in the saved metric definition.
Neither raw sign accuracy nor RMSE includes transaction costs.

The selected epochs were MLP 17/29/43 at epochs 5/4/3, and GRU 17/29/43 at
epochs 3/6/4. Training stopped after 8/7/6 and 6/9/7 epochs respectively.
The six model fits took about 114 seconds in total on the installed PyTorch
2.12.1 CPU runtime. Saved weights reproduce each full validation prediction
exactly after reload. Separate sampled inference reproduced 192 rows across
training, validation and evaluation with zero measured difference for all six
neural checkpoints.

The account gate requires absolute predicted gross return minus decision-time
estimated fees and both execution-cost legs to exceed 2 bps. The account
reserves positions and capital before delayed candle-reference fills. Equity
resets to Rs 500,000 daily, with three positions, Rs 100,000 maximum notional
per position and a Rs 2,500 realized-loss admission stop. These are proxy
accounts with no verified bid/ask, capacity or intratrade mark-to-market.

| Variant, evaluation at 2 bps per leg | Trades | Gross PnL after execution costs | Fees | Net PnL |
| --- | ---: | ---: | ---: | ---: |
| Training-mean constant | 0 | Rs 0.00 | Rs 0.00 | Rs 0.00 |
| Zero-return persistence | 0 | Rs 0.00 | Rs 0.00 | Rs 0.00 |
| Summary ridge | 43 | Rs 712.51 | Rs 3,545.26 | -Rs 2,832.75 |
| MLP seed 17 | 65 | -Rs 10,278.59 | Rs 5,361.90 | -Rs 15,640.49 |
| MLP seed 29 | 57 | Rs 1,561.26 | Rs 4,695.52 | -Rs 3,134.26 |
| MLP seed 43 | 33 | Rs 2,620.48 | Rs 2,726.06 | -Rs 105.58 |
| MLP equal seed average | 4 | -Rs 1,980.92 | Rs 330.69 | -Rs 2,311.61 |
| GRU seed 17 | 41 | -Rs 5,451.80 | Rs 3,388.85 | -Rs 8,840.65 |
| GRU seed 29 | 61 | -Rs 3,189.04 | Rs 5,033.09 | -Rs 8,222.13 |
| GRU seed 43 | 20 | -Rs 1,209.42 | Rs 1,650.66 | -Rs 2,860.08 |
| GRU equal seed average, selected on validation | 23 | -Rs 3,883.16 | Rs 1,901.31 | -Rs 5,784.47 |

Each row is a separate account and overlapping signals are not additive.
Sparse trades do not establish a stable risk estimate. The selected GRU
average had nine profitable evaluation trades out of 23, a 39.13% net trade
win rate. This differs from its all-row raw sign accuracy of 51.07%.

The selected GRU average made Rs 4,411.86 on 36 validation trades at 2 bps
per leg, then lost Rs 5,784.47 on evaluation. At 5 bps per leg it made
Rs 8,705.71 on only nine validation trades and admitted no evaluation trades.
At 10 bps it admitted no validation or evaluation trades. Increasing assumed
costs also tightens admission and changes the selected trade sample. A positive
sparse validation subset is not evidence that higher costs improve a fixed
strategy's fills or that the model has a reliable edge.

All 66 planned account comparisons completed across 11 variants, validation
and evaluation, and three execution-cost sensitivities. Ten focused tests
passed before fitting. The additive audit checked source and model fingerprints,
exact dataset row identities, recreation of scalers from training only,
validation-only selection, seed averages, saved-weight inference, and all 66
trade/daily ledgers for chronology, accounting and position limits.

The shared dataset's ex-post full-session eligibility, current survivor
coverage, unverified corporate actions and candle timestamp labels limit
interpretation. Historical candles do not establish spread, quote freshness,
size capacity, source delay, queue position or market impact. Existing fee
tariffs applied to older history are a counterfactual sensitivity. No untouched
prospective holdout or model-promotion claim follows from these results.

Evidence lives in `runs/initial-v1/predictions.parquet`, `forecast-metrics.csv`,
`account-metrics.json`, each account's trade and daily ledgers, `.pt` model
weights, `scaler.json`, `ridge.npz` and `frozen-selection.json`. Independent
audit evidence is in `audits/initial-v1/report.json`. Nothing connected to a
broker and no production trading code changed.
