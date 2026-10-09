# Sources inspected on 2026-10-01

| Primary source | Evidence | Use in this track |
|---|---|---|
| [Dhan pricing](https://dhan.co/pricing/) | NSE cash intraday brokerage is the lower of Rs20 and 0.03% per executed order; transaction and other statutory charges are listed. Detailed charges require contract-note reconciliation. | Existing frozen lab fee model retained for comparability. We vary latency, slippage, and footprint rather than changing tariffs to make a strategy win. |
| [DhanHQ API introduction](https://dhanhq.co/docs/v2/) | Broker REST order API limits include 10 requests/second and separate minute/hour/day caps; modifications have a separate per-order cap. | Retail broker submission capacity and API latency are different quantities. No authentication, credentials, or live requests are used in this research. |
| [hftbacktest fill documentation](https://hftbacktest.readthedocs.io/en/latest/order_fill.html) | Replay cannot change the market; liquidity-taking fills can be unrealistic; queue position requires modeling when unavailable. | A smaller footprint sensitivity does not prove executable top-quote capacity. Model error remains even with conservative parameters. |
| [hftbacktest maintained repository](https://github.com/nkaz001/hftbacktest) | Full L2/L3 book, queue-position and feed/order latency modeling; current live examples concern crypto venues. | Future execution-model reference after richer recording. No repository scripts were executed, and its crypto examples do not establish broker execution for NSE. |

The 3-second delay and 3 bps slippage scenario are hypothetical stress assumptions. The sources do not calibrate them for this account or route.
