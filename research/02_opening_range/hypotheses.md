# Frozen hypotheses before initial runs

October 1, 2026. No parameter choices below use this track's results.

1. `orb15`: complete fifteen-minute observed opening range, either direction breakout by the common three-basis-point confirmation buffer, one signal per stock, no VWAP filter.
2. `orb30_direction`: thirty-minute range, same buffer, only a breakout matching the opening midpoint direction.
3. `orb15_vwap`: fifteen-minute range plus supplied-VWAP direction alignment. Unknown VWAP blocks the signal.

Common risk, cash fees, spread limit, next-observation bid/ask execution and delay remain the shared runner defaults. Opening-specific admission starts are 09:30 and 09:45 IST. No ATR exits or stocks-in-play ranking are claimed.

Development dates are August 19, 20, 21. Diagnostic validation is August 24, 25. Later audit dates are August 31 and September 1. The universe is fixed using August 18 top twelve historical ADV. These sessions have already been inspected elsewhere, so validation and audit are chronological diagnostics rather than untouched final holdouts.

Report all hypotheses in both strict and receipt-proxy modes, including zero-entry and incomplete-data outcomes. Do not tune on validation or audit outcomes. Any next hypothesis needs a new version and independent data.
