# Initial volatility-compression findings

October 1, 2026. The tested compression entries do not establish net directional continuation. The absolute-band and close-channel adaptations lose before fees in receipt-proxy sensitivity. The relative-width rule has only one trade and remains too data-sparse to evaluate.

## What ran

Three frozen variants, seven sessions, strict and receipt-proxy modes yield 42 policy/session replays. Every variant observes the same 1,154,473 retained twelve-stock receipts across the dates. The engine waits for later usable bid/ask observations, adds hypothetical per-side slippage and cash fees, limits risk and exposure, and saves incomplete states explicitly.

Twelve behavioral tests pass and Python compilation passes. Tests check completed-minute causality, two-close confirmation, shorts, continuity gaps, unknown or explicitly bad freshness, current-price reversal, flat bands, full 125-width warmup, separate stock histories and timestamp ordering. Saved output is in `test-results.txt`.

## Receipt-proxy sensitivity

Amounts are rupees, summed across separate daily accounts. This mode does not verify source quote age or actual exchange execution.

| Hypothesis | Trades | Gross P&L | Fees | Net P&L | Positive sessions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bollinger relative 125-width low | 1 | -188.29 | 82.68 | -270.97 | 0 |
| Bollinger absolute width at most 15 bps | 46 | -1,858.08 | 3,649.52 | -5,507.60 | 0 |
| Prior five-close compressed channel | 138 | -6,782.08 | 10,808.84 | -17,590.92 | 0 |

| Hypothesis | Development net | Diagnostic validation net | Historical audit net |
| --- | ---: | ---: | ---: |
| Relative bandwidth | 0.00 | 0.00 | -270.97 |
| Absolute bandwidth | -2,230.85 | -1,705.31 | -1,571.45 |
| Compressed channel | -7,565.64 | -5,032.20 | -4,993.08 |

The absolute-band policy emits fifty signals and fills 46 trades. Twelve stop, 33 time out and one reaches its target. The channel emits 2,707 signals, but the account fills 138 trades. The daily-loss action triggers on every date and subsequently rejects 2,075 signals. Those rejections make trading opportunity dependent on earlier account outcomes; averaging all raw signals would not describe a feasible portfolio.

The channel exits comprise forty stops, 79 time exits, two targets and seventeen daily-loss exits. Its largest marked drawdown is Rs 2,704.55. A Rs 2,500 loss threshold initiates delayed exits and can be exceeded. Every replay ends without unresolved positions or pending entries.

Strict mode admits one channel trade on August 25 with net P&L of -253.95. Neither Bollinger variant trades in strict mode. Sparse source-quality eligibility cannot support a live strategy conclusion from this mode.

## What this means

The observed compression signal is not enough by itself. Larger subsequent movement and profitable direction are different outcomes. Costs account for Rs 10,808.84 of the channel loss, but even eliminating fees would leave this configuration negative. Improving fee calculations alone cannot repair that result.

The relative rule needs twenty completed closes plus 125 prior width measurements on a continuously usable observed tape. It trades only once, on September 1 in proxy mode. That is insufficient to infer either positive or negative expected returns. The tests demonstrate that a full synthetic squeeze history triggers correctly, so zero trading on six days is retained as data and opportunity evidence rather than bypassed through shorter warmup.

The [Bollinger manual](https://www.bollingerbands.com/_files/ugd/58be43_d09c50b6e8ea4afd9af0523ef94de876.pdf) also interprets confirmed breaks with ADX; this adaptation omits that condition. We test quote closes rather than complete trade bars. Results do not constitute Method IV replication. The [daily-market paper](https://acfr.aut.ac.nz/__data/assets/pdf_file/0007/29896/100009-Popularity-vs-Profitability-BB-August-Final.pdf) motivates testing rather than trusting indicator popularity, but it does not directly establish this intraday result.

## Evidence and next work

`runs/initial-v1` preserves plan, source snapshot, input manifests, every session summary and trade journal. A receipt-proxy August 25 repeat lives in `runs/repeat-check-v1` with exact checks in `repeatability.json`.

Keep these failed and sparse hypotheses frozen. Next collect continuous timing-verified data and test absolute-move expansion separately from directional net returns. Any ADX, volume or alternative holding-period extension needs a new preregistered version and independent dates. Increasing tested combinations on the same seven days would make the best historical result less trustworthy.
