# Primary sources inspected on 2026-10-01

| Source | Evidence | How it affects this experiment |
|---|---|---|
| [QuantConnect relative daily volume documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/relative-daily-volume) | Compares cumulative session volume with historical cumulative volume at the same time of day. | Supports controlling for intraday seasonality. We instead compare incremental completed-minute volume, so this is not an exact RDV reproduction. |
| [Official LEAN implementation](https://github.com/QuantConnect/Lean/blob/master/Indicators/RelativeDailyVolume.cs) | Open implementation of the documented cumulative indicator. | Source inspected for indicator semantics. No external code was downloaded or executed. Our private adapter attaches recorded cumulative volume to exact receipt identities. |
| [Lee and Swaminathan, price momentum and volume](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00280) | Primary publication studies interactions of trading volume and price momentum across substantially longer portfolio formation and holding periods. | Motivates distinct continuation and reversal hypotheses. Its empirical results do not transfer to our intraday thresholds. |
| [Gopikrishnan and coauthors, share volume](https://arxiv.org/abs/cond-mat/0008113) | Research on traded-volume distributions and the roles of trading count and volume in equal-time price relationships. | Volume-price association is not itself future return evidence; we test later executable outcomes. |
| [Dhan market feed documentation](https://dhanhq.co/docs/v2/live-market-feed/) | Defines fields in the broker's live market feed. | Historical `day_volume` is interpreted as a received cumulative-volume field, with monotonicity checked. Its source update clock is not established by our derived recording. |

Three development days are a deliberately small minimum, not proof of a dependable seasonal volume forecast. Hypotheses and data gates were fixed before evaluation.
