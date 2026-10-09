# Variance-ratio findings

Three frozen variants completed42 policy/session replays. Every strict-mode variant produced zero trades because continuous eligible history is insufficient under the conservative source-evidence gates.

| Receipt-proxy variant | Trades | Gross P&L, Rs | Fees, Rs | Net P&L, Rs |
|---|---:|---:|---:|---:|
| Trend, lag2 |63|-1,433.26|4,912.79|-6,346.05|
| Adaptive direction, lag2 |133|-4,446.54|10,060.03|-14,506.57|
| Adaptive direction, lag5 |179|-3,084.39|13,661.42|-16,745.81|

All receipt-proxy variants lose before fees and have no positive net session. Every replay ends without unresolved positions. Loss limits and different eligible signals change exposure, so this table does not rank model quality independently of account behavior.

The ratio is a descriptive variance estimate on30 completed-minute logreturns, not a formal significance test. We did not implement the original paper's debiasing and heteroskedasticity-robust statistics. Short windows, irregular quote activity, and unverified source timing can distort the descriptor.

Tests verify alternating-return and zero-variance cases, invalid windows, and missing-minute handling. The runner rejects future/incorrect signal identity and applies common fees/risk. [Method and reviewed papers/repository](C:/Users/prajw/Downloads/Trader/research/09_variance_ratio/README.md), [saved comparisons](C:/Users/prajw/Downloads/Trader/research/09_variance_ratio/runs/initial-v1/comparison.csv).

No deployable regime classifier has been established. Better data and more independent sessions are required before comparing this descriptor with volatility, trend-efficiency, or fitted regime models.
