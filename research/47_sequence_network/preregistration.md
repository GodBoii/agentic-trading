# Sequence comparison frozen before fitting

Declared 2026-10-09 before any model fitting or evaluation for this track.
Use the shared track 45 cohort, selected only by 2022 median turnover among
stocks with at least 150 full sessions. Training is 2022-2023, validation is
2024, evaluation is 2025-2026. This historical data was collected earlier and
does not establish an untouched prospective holdout.

Primary target is entry-open to 15-minute-later-open raw return in bps.
The shared label delays entry by one full minute after decision availability.
A candle starting at t completes at t+1 minute, then entry uses the t+2 minute
open. Exit uses the t+2+15 minute open, allowing a full processing-delay budget.
All variants use the same complete-label and contiguous-history rows. Thirty
completed one-minute bars provide a causal sequence. Decisions occur every
15 minutes from 09:45 through 14:45. Actual input channel/context definitions
and exact shared dataset hashes will be recorded with the run before fitting.

Compare a training-mean constant, zero-return persistence, summary ridge,
tabular MLP, and forward GRU. Tabular inputs concatenate shared causal context
with each sequence channel's mean, standard deviation, last value and cumulative
sum. The MLP uses Linear(input,32), ReLU, Linear(32,16), ReLU, Linear(16,1).
GRU uses a single forward layer with hidden size 16, no dropout or bidirectionality.
Its final hidden state concatenates the same shared context, then Linear(16+context,16),
ReLU and Linear(16,1). GRU therefore tests chronological order information that
the summary controls do not retain. No attention, smoothing or future context.

Three fixed neural seeds are 17, 29 and 43, all reported individually. Also
report their equal arithmetic prediction average separately for each architecture.
Never choose a seed from evaluation returns. A descriptive validation-only
winner may be identified, with no claim that it has positive trading performance.

Training-only feature means and standard deviations scale channel observations
across training sequences, and context columns across training rows. Constant
columns receive scale 1. Raw target mean/standard deviation are fitted from
training only. Neither validation nor test enters normalization. Standardized
inputs are clipped at +-10 under a frozen rule to limit outlier numerical impact.
Targets are standardized for loss and converted back to bps for predictions.

Ridge minimizes mean squared normalized target error plus 0.01 times squared
non-intercept coefficients. Neural training uses PyTorch 2.12.1 CPU, float32,
two CPU threads, deterministic algorithms, AdamW learning rate 0.001 and weight
decay 0.001, MSE, batch size 512, gradient norm cap 5, shuffled training rows
with a seed-specific generator. Maximum 12 epochs, early stopping after three
consecutive epochs without a validation MSE improvement of at least 1e-6.
Validation selects a checkpoint only. Save all six selected model weights,
scalers and learning histories before computing test predictions or metrics.
The shared loader may return all chronological arrays together; only the declared
train and validation masks may enter fitting, normalization or checkpointing.

Evaluate RMSE, MAE, raw-return sign accuracy with zero labels excluded and
training-majority direction/persistence controls on identical rows. Keep all
row identities, labels and predictions. Cost/account metrics use the shared
candle proxy with frozen admission thresholds and costs; a prediction metric
alone never establishes account profitability. Candle history does not verify
bid/ask spreads, queue, source latency or market impact. No model is promoted.
Net-edge threshold is 2 bps after estimated fees and two execution-cost legs.
Run 2, 5 and 10 bps per-leg cost sensitivities for every variant on validation
and test. The proxy resets Rs 500,000 equity each day, limits positions to three
and each position to Rs 100,000, and stops admission after Rs 2,500 realized
daily loss. It reserves capital and slots at decisions before delayed fills.

Target 15 minutes is primary. Additional horizons require a new preregistered
version before fitting and must not be selected from test performance.

The five sequence channels are ret1 bps, candle body bps, candle range bps,
log1p of current volume divided by preceding rolling mean volume, and cumulative
session VWAP deviation bps. Shared 21-column context includes price/volume
summaries, prior-session same-slot volume ratio, overnight gap, synchronized
leave-one-out peer and residual returns, and intraday sine/cosine. Full-session
eligibility is an ex-post data filter, and available files reflect current
survivor coverage. Both limit historical interpretation.

