# Minute sequence neural comparison

This track compares a small forward GRU with a tabular neural network, ridge,
training-mean and zero-return controls. All use the same shared historical
rows, chronological train/validation/test dates and causal completed-minute
information. The primary target is the raw 15-minute entry-to-exit return.

The GRU processes 30 minute observations in order and combines its final state
with 21 context inputs. The MLP and ridge use the context plus sequence summary
statistics. Three fixed seeds are retained individually, and each architecture
also has an equal prediction average. Validation selects training checkpoints;
evaluation cannot change weights, seeds, thresholds or model parameters.

Read [the preregistration](preregistration.md) before interpreting results.
[Findings](findings.md) describe the completed six neural fits and 66 account
comparisons. The selected GRU average did not beat simple evaluation controls
and lost Rs 5,784.47 in its primary simulated evaluation account.
[Sources](sources.md) document official PyTorch formulas and runtime controls.
`network.py` contains train-only scalers and models. `run.py` freezes fitted
weights before evaluation, retains every row forecast, and applies the shared
delayed candle account proxy at three cost levels. These are simulated
historical accounts with no observed spread, capacity or intratrade marks.

Run from the repository root with:

```
python -m research.47_sequence_network.run --dataset-module research.45_market_dataset.dataset --account-module research.45_market_dataset.account
python -m pytest research/47_sequence_network/tests -q
python -m research.47_sequence_network.audit
```

Evidence is versioned and the runner refuses to overwrite `runs/initial-v1`.
Models are research artifacts and have no broker connection.
