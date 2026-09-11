# Candidate priority experiments

Written before computing the new feature/outcome comparisons.

Use September 2 and 3 for development, September 7 for validation, and September
8 and 9 for a fixed-rule confirmation comparison. All dates have previously been
inspected, so none is an untouched holdout. Do not tune against September 10's
live session. A later untouched session is required for a deployment decision.

Use only completed observed minutes before each five-minute boundary. Do not
forward-fill gaps. Require fresh quotes and five observed future minutes for
labels. Report missing labels and selections separately. Treat stocks and dates
as correlated observations; do not interpret thousands of overlapping events as
independent proof.

Primary discovery outcome: absolute five-minute close displacement of at least
0.5%, with future close-path efficiency at least 0.6. Also report median absolute
displacement, maximum favorable movement in either direction, spread and turnover.
The latter is a hindsight opportunity measure, not profit a strategy could earn.
Repeat the primary result after an entry-spread allowance. No fee/slippage-free
P&L claim is permitted.

Compare up to ten selections at each boundary, from the same eligible top-100
recorded activity population. Preserve all missing-label selections in counts.

Fixed hypotheses:

1. Existing activity rank.
2. Recent range: highest latest-minute range.
3. Fresh movement: latest-minute/five-minute range ratio times a rank weight,
   `(101 - recorded_rank) / 100`, within the top-100 population.
4. Renewed volume: latest-minute volume divided by the preceding five-minute
   average, times that rank weight, with ratio capped at three.
5. Efficient movement: five-minute close-path efficiency times that rank weight.
6. Volume plus fresh movement: minimum percentile of volume renewal and latest
   range, breaking ties with original activity rank.
7. Expansion after compression: latest range divided by preceding five-minute
   median range, times volume renewal, both capped at three.
8. Liquidity: recent five-minute traded value, as an execution-quality control.

No threshold grid, fitted weighted score or machine-learning model in this pass.
Patterns that improve one day but deteriorate elsewhere stay research-only.
Admission bottlenecks and signal-to-entry delays are evaluated separately.

The minute export does not contain the raw hotness score. The rank weight above
is the explicit surrogate used by the initial implementation, documented before
opening validation/holdout results. Decisions start at 09:25 so these tests do
not validate opening signals during the first ten minutes.

At 20:30 IST on September 10, after the session closed and these rules were
already frozen, its completed tape was exported for an untouched comparison.
No price/outcome from that date had been inspected in this task before freezing
the rules. Use it once for the final comparison; do not retune afterward.
