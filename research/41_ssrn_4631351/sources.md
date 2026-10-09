# Sources and paper review

Reviewed on 2026-10-09.

- User-supplied `research/ssrn-4631351.pdf`, 26 pages. SHA-256 `47137abd00730dd6970d5d6409b3908342d63d75ecfc9cf2badc7d206f6905c8`. PDF creation/modification metadata is 2025-04-29. The extraction is `paper-extracted.txt`; all pages were read. This supplied PDF is the source for the detailed method below.
- [SSRN abstract and publication record](https://papers.ssrn.com/sol 3/papers.cfm?abstract_id=4631351), Zarattini and Aziz, Volume Weighted Average Price, The Holy Grail for Day Trading Systems. Written 2023-11-13, revised 2025-04-29. Search returned the publication record; directly opening the abstract returned an internal error. The supplied local paper provided the text.
- [Author-hosted paper](https://concretumgroup.com/wp-content/uploads/2026/02/Volume-Weighted-Average-Price.pdf). Search located this primary copy. We evaluated the supplied file and recorded its hash rather than replacing it with a possibly different copy.
- Fee implementation is the existing `research/intraday_lab/costs.py`. Its frozen source cites [Dhan pricing](https://dhan.co/pricing/) and labels its assumptions effective 2026-09-30. This experiment reuses that tariff as an assumption, does not independently certify historical fees, and hashes the implementation in its run plan.

## What the supplied paper actually specifies

Pages 2-3 define one-minute typical price `TP_t=(H_t+L_t+C_t)/3` and a regular-session cumulative VWAP `sum(TP_t*V_t)/sum(V_t)`. Page 5 describes the US QQQ/TQQQ minute OHLCV sample and data providers. Pages 8-11 specify completed-minute close relative to VWAP, entry after the minute closes, reversal when a later completed close crosses VWAP, and flattening at the regular-session end. Intraminute crossings alone do not exit. Page 9 allocates the account's entire equity without leverage. Pages 9-10 assume zero slippage and charge USD 0.0005 per share.

The short-entry sentence on page 8 mentions the first candle's open, while the surrounding definition, long entry and worked examples use the completed close. This adaptation consistently uses the completed close and makes the execution delay explicit.

Pages 12-18 report results and trade asymmetry. Pages 19-20 compare the VWAP signal against SMA 9/20/100/200 controls. Pages 21-23 analyze time-of-day PnL and offer possible institutional execution explanations. Those explanations are hypotheses about behavior, not evidence of a causal mechanism.

This is a directional trading rule, not a fitted multi-factor probability model. Volume weights the average price inside its VWAP calculation. The paper does not learn weights across strategies, calibrate outcome probabilities, or combine an ensemble of predictors. A higher trade hit rate is also not its sole objective: the paper's table 4 reports roughly 17% winning trades balanced by larger winners.

## What was transferred and what changed

The candle experiment transfers the paper's typical-price VWAP formula, completed-close direction, next-minute execution, crossover reversals, full-equity integer sizing and end-of-session liquidation. It substitutes NSE stocks for the original ETFs and local candle files for the original database. Indian intraday costs replace the paper's US per-share assumption. Adverse slippage has predeclared 0/1/5 bps scenarios. Candle timestamps are floored to their minute bucket, and their labeling convention has not been independently confirmed with the data vendor. The last regular candle's close approximates scheduled end-of-session liquidation. No quote-spread or fill-capacity model can be recovered from these candles.

The second candle variant adds an original, fixed momentum/path-efficiency confirmation filter. That filter is not claimed to come from SSRN 4631351. It requires six completed closes, five-minute same-direction return of at least 8 bps, a latest-minute same-direction return, and efficiency of at least 0.3. It exits to cash when the filter fails. No outcome-driven weights are fitted.

The separate quote experiment uses the vendor VWAP field and completed midpoint bars, then the existing shared fixed target/stop/horizon engine. This compares entry information under the common execution model. Its fixed exits and restricted entry schedule do not reproduce the paper's trading rule.

## Exact replication prerequisites not supplied

Exact reproduction of the published QQQ/TQQQ figures would require the original 2018-2023 ETF minute OHLCV, the original data treatment and executable MATLAB details, US fees and funding assumptions, and precise corporate-action conventions. The NSE experiments answer whether the transferred rule works in the saved local data under explicit assumptions. They do not reproduce the published figures or establish a deployable edge.
