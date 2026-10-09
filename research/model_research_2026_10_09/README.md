# Model, parameter and feature research

Completed October 9,2026 with three subagents and a coordinating feature study. All discussed approaches received actual offline experiments: richer inputs, bounded parameter searches, multi-horizon targets, boosted trees, sequence neural networks and controlled retraining. None of the tested models established a reliable later-period forecasting or trading edge. Positive sparse outcomes remain visible as hypotheses rather than being discarded or promoted.

## Shared experiment

The [shared dataset and account](../45_market_dataset/README.md) contains 277,704 aligned observations across twelve stocks. Stock selection used only 2022 median daily traded value from the locally available minute histories, with at least 150 complete sessions. Training has 119,238 observations on 485 dates in 2022-2023; validation has 61,719 on 245 dates in 2024; later evaluation has 96,747 on 384 dates in 2025-2026. The available data endsJuly 24,2026. Current-survivor/download selection remains a limitation.

Features use only completed minute candles. Proposed decisions are spaced fifteen minutes apart, with a full minute between feature availability and entry reference. Targets measure gross return over 5,15 or 30 minutes after that delayed entry. The same cohort supplies all model comparisons. There is no shuffled date split or training label extending into a later phase.

The deterministic account reserves cash and one of three slots at each admitted decision, allows one position per stock, fills at the delayed candle reference, charges fees, and releases capital only at scheduled exit. Each date starts withRs 500,000 and up toRs 100,000 per position. A realized-loss entry halt stops new admissions afterRs 2,500. This is not a guaranteed maximum loss or intratrade stop. Execution-cost assumptions are 2 and 5 bps per leg, with an additional 10 bps neural stress. These are hypothetical reference fills, not measured broker spreads or capacity.

## What was tested and observed

| Track | Actual comparison | Observation |
|---|---|---|
| [46, parameters and trees](../46_horizons_trees/findings.md) | Momentum lookbacks 5/15/30 minutes, two entry margins, ridge and histogram gradient boosting with three margins, across 5/15/30 minute targets |36 active validation candidates. All nine policies selected abstention under the preregistered cost and minimum-trade requirements. Underlying boosted forecasts remained worse than constant controls on later data. |
| [47, sequence neural networks](../47_sequence_network/findings.md) | Actual PyTorch GRU and tabular MLP, three fixed seeds each, ridge and simple controls, identical fifteen-minute outcomes |The GRU seed average slightly improved validation error, then lost to simple controls on later data. Its primary account lostRs 5,784.47 across 23 trades. |
| [48, controlled adaptation](../48_controlled_adaptation/findings.md) | Static ridge, monthly expanding, rolling twelve-month and recent-data weighted fitting at all three horizons; a controlled fifteen-minute update policy |All thirteen later method/horizon cases lost to zero-return prediction on MAE and RMSE. The update gate rejected 28 eligible challengers and retained the original model. |
| [49, richer information](../49_feature_ablation/findings.md) | Hold ridge complexity fixed while adding own-volume, synchronized peer/residual returns and time/gap context |Small improvements over the price/VWAP version at fifteen/thirty minutes, but no feature set beat the training-mean forecast. A small positive peer result failed the higher-cost sensitivity. |

There are 287 account evaluations with saved trade/daily ledgers:57 parameter/tree accounts,66 neural accounts,104 adaptation accounts and 60 feature accounts. They repeat stocks, dates, horizons, years and cost scenarios, so they are not 287 independent trials. Selector shadow utility comparisons are additional internal checks, separate from this saved-account count.

## Promising outcomes were not hidden

The fifteen-minute boosting candidate at a 10 bps additional net margin madeRs 29,278.11 over 91 validation trades. It fell below the frozen 100-trade requirement. Other positive tree/ridge validation candidates were even sparser. We retained their forecasts and results and did not change the requirement after seeing them. This is a candidate for a new preregistered study, not proof that its 91 trades were uninformative or a deployment recommendation. The chosen no-trade policy was evaluated later; this run did not execute the rejected 91-trade candidate on test as a new selected winner.

Expanding retraining madeRs 2,293.16 over nine fifteen-minute evaluation trades, decreasing toRs 1.54 over four trades at 5 bps per leg. At thirty minutes it madeRs 2,449.87 over 41 trades, but its 2026 slice lostRs 1,082.93. Peer features madeRs 804.36 over 88 thirty-minute trades at 2 bps, becoming aRs 502.98 loss under 5 bps.

Higher assumed costs also tighten the entry gate and change which opportunities trade. Their account differences are not isolated cost changes applied to an identical trade set. We did not select a new threshold, horizon or seed using these later outcomes.

## Neural learning and accuracy

The GRU is a one-layer forward recurrent model with sixteen hidden units and 1,729 parameters. The MLP has 1,889 parameters. Both see the same 21 context features; the GRU processes thirty ordered completed bars with five channels, while the MLP sees sequence summaries. Three fixed seeds 17/29/43 were retained individually and equally averaged. Training-only scalers and target normalization prevent evaluation data affecting learning. Validation selects checkpoints through fixed early stopping. Six fits took about 114 seconds on the installed CPU runtime.

| Fifteen-minute predictor | Validation RMSE bps | Later RMSE bps | Later direction accuracy |
|---|---:|---:|---:|
| Zero-return persistence |38.78793|32.70056|No direction prediction|
| Training-mean constant |38.78578|32.70363|51.80%|
| MLP seed average |38.79580|32.71674|50.75%|
| GRU seed average, selected on validation |38.77312|32.73036|51.07%|

The selected GRU's 0.01266 bps validation RMSE improvement over the constant did not persist. Its primary later account lostRs 5,784.47, with nine profitable trades out of 23. Raw direction accuracy 51.07% and net trade win rate 39.13% describe different outcomes. Neither demonstrates an advantage over the simple controls.

Boosting later direction accuracy was 50.99%,51.34% and 51.94% at 5/15/30 minutes. The frozen constant direction achieved 51.91%,51.80% and 52.35%. All corresponding tree and ridge R² values versus the training mean were negative. Reporting only approximately 52% would hide the stronger simple benchmark.

## How retraining behaved

Scheduled models trained only on labels mature before each monthly boundary. Rolling models used twelve calendar months; recency models assigned a fixed ninety-observed-date half-life. Deployed coefficients remained unchanged throughout their month.

The controlled policy compared its actual deployed model with shadow candidates on sixty earlier dates outside that model's training history. A challenger needed at least 1% lower MAE and nonnegative account utility no worse than the incumbent. After a successful refit it would wait for sixty fresh dates before another honest comparison. The actual run had 31 boundaries, three initial waiting decisions and 28 rejections, with zero switches. Synthetic tests exercised acceptance and the subsequent unseen-data wait. This proves the fallback and timing behavior were exercised, not that adaptive switching became profitable.

The study tested practical update baselines motivated by [DoubleAdapt](https://arxiv.org/abs/2306.09862). It did not implement DoubleAdapt's learned data/model adapters or claim a reproduction of its reported results. The neural study used official [PyTorch GRU](https://docs.pytorch.org/docs/stable/generated/torch.nn.GRU.html) and optimizer references; it did not implement DeepLOB because the candle history lacks its order-book sequences. Histogram boosting follows the installed scikit-learn implementation with parameters frozen before evaluation. Primary references and implementation differences are recorded in each track's sources.md.

## Functionality and evidence checks

The focused tests exercise future-prefix invariance, train-only scaling, GRU gradients, deterministic training/checkpoint reload, chronological phase boundaries, label maturity, immutable deployed weights, update acceptance/rejection, delayed order arrival, capital and slot reservations, non-overlapping stock exposure, fees and loss halts. Independent checks reconstruct frozen ridge and boosted-tree predictions and safely reload neural weights for inference.

The complete research suite passed 257 tests, including 42 new checks in this batch. Python compilation also passed for all new research modules.

Track 49's first verifier was missing strict file-coverage and saved-result/hash comparisons. Review found the gaps while the actual evidence was complete. A separate stronger version now demands all six prediction files and sixty accounts, reconciles saved RMSE and PnL with ledgers, and checks model/input fingerprints. The earlier report remains preserved. Corruption tests reject missing and extra evidence.

The integrated verifier checks ninety-two distinct original selection/candle inputs, all 277,704 aligned rows, all target intervals and gross labels, and the exact planned account files across every track. Model-level audits verify saved coefficient/weight state, forecast identity, fee arithmetic and account chronology. A passing audit proves implementation and arithmetic behavior, not predictive significance or actual achievable fills.

## Interpretation and remaining scope

The experiments support retaining simple controls and refusing automatic deployment of these particular models. They do not establish that all neural networks, feature sets or parameter values fail. The tests are bounded, and many related hypotheses have now been inspected. A larger network trained on the same data might find a better fit, but that improvement would still need independent chronological evidence and measured execution economics.

The actual histories do not supply synchronized true index/sector series, historical news available-at-time records, or a complete timestamp-verified trade/book tape. Peer signals were explicitly proxies; absent inputs were not fabricated. Historical source quote age, corporate-action adjustment and candle labeling are unverified. Ex-post complete-session filtering and current-survivor selection limit every result. No pristine prospective holdout claim applies to these already available files.

The tested hybrid is implemented: causal market features feed numerical forecasts, and deterministic account rules decide whether a trade qualifies. What has not been demonstrated is useful alpha after costs. Production integration, broker execution, exchange HFT, online live updating and deployment remain outside these offline experiments. No live orders or production settings changed.

The next scientifically distinct test can preregister the sparse boosting candidate on fresh dates with measured quote/fill data and explicit uncertainty, without changing its gate based on these results. Genuine sector/index or timestamped event inputs would test information absent from this batch. Current data supports neither a guaranteed return nor a chosen profitable neural model.

## Evidence and reproduction

Each track provides its commands, exact specification and findings. Complete source snapshots, fitted states, prediction rows and trade/daily ledgers remain local in ignored cache/run directories. Compact result summaries, manifests, audit reports and source are versioned for review. Credentials and raw downloaded market files are excluded.

```powershell
python -m pytest --import-mode=importlib research/45_market_dataset/tests research/46_horizons_trees/test_methods.py research/47_sequence_network/tests research/48_controlled_adaptation/tests research/49_feature_ablation/tests research/model_research_2026_10_09/tests -q
python -m research.model_research_2026_10_09.verify
```

Existing run and report paths refuse overwriting. A changed experiment requires a new specification/output version. See verification.json and test-report.json for this completed batch's checks.
