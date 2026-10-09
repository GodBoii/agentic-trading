# Primary implementation references

Read on 2026-10-09. Installed runtime is PyTorch 2.12.1 CPU.

- [PyTorch 2.12 GRU documentation](https://docs.pytorch.org/docs/2.12/generated/torch.nn.GRU.html).
  Defines reset and update gates and recurrent hidden-state recursion. This track
  uses one forward layer, hidden size 16, with the final hidden state as a summary
  of 30 already completed minute observations. No future-facing recurrence runs.
- [PyTorch 2.12 AdamW documentation](https://docs.pytorch.org/docs/2.12/generated/torch.optim.AdamW.html).
  Defines adaptive moment estimates with decoupled weight decay. This track uses
  fixed learning rate 0.001, weight decay 0.001 and the standard implementation.
- [PyTorch 2.12 reproducibility documentation](https://docs.pytorch.org/docs/2.12/notes/randomness.html).
  Documents seed controls and deterministic algorithms and explains that exact
  reproducibility is not guaranteed across releases or platforms. This track
  saves runtime versions, fixed seeds and actual model weights. Determinism claims
  apply to the tested CPU environment, not arbitrary machines.

These references explain computations and controls. They contain no claim that
this architecture predicts the local equity market profitably. Performance
claims must come from the track's chronological prediction and account evidence.
