# Frozen variance forecast comparisons

October 1, 2026. No trading account, directional prediction or parameter fitting.

Compare EWMA decay 0.94, EWMA decay 0.97 and a thirty-completed-return equal-weight mean of squared log returns. Both EWMA models seed from the same first thirty contiguous completed returns. Seed, floor and rolling length are fixed before inspecting results. Positive forecast variance floor is 1e-12 in decimal log-return squared units. Score next-minute squared log midpoint return using MSE and Gaussian QLIKE, log forecast plus observed squared return divided by forecast.

Minute closes include only prior receipts. Forecast clock is the subsequent exact minute boundary. Require usable receipts, first/last receipt within fifteen seconds of the minute boundaries and no larger receipt gap. Reset histories after invalid bars or missing minutes; do not bridge overnight. Score all models on the same thirty-return-warmed pairs and retain zero realized returns. No forward filling, cross-session seeds, outcome trimming or lambda selection.

Use the fixed prior August 18 twelve-stock ADV cohort and seven common diagnostic dates, strict and receipt-proxy modes. Report sample counts, source/input/output hashes and chronological development/validation/audit groups. Previously inspected dates and unknown quote age prohibit promotion or trading profitability claims.
