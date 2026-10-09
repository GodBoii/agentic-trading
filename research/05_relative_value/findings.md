# Relative-value proxy findings

The first batch completed42 policy/session replays across seven dates, three frozen variants, and two freshness modes. This is an unhedged relative-return adaptation, not a cointegrated two-leg portfolio.

| Receipt-proxy variant | Trades | Gross P&L, Rs | Fees, Rs | Net P&L, Rs |
|---|---:|---:|---:|---:|
| Peer continuation |151|-6,389.37|11,426.20|-17,815.57|
| Peer reversal |165|-5,275.65|12,466.26|-17,741.91|
| Confirmed reversal |178|-3,837.07|13,157.43|-16,994.50|

All three proxy variants lose before fees and have no positive net session. Every replay ends without unresolved exposure. Loss halts censor trading opportunities, so a lower aggregate loss across variants is not proof of a better forecast.

Strict mode admits only two continuation trades, two reversal trades, and one confirmed-reversal trade. The two strict reversal trades together earn Rs424.41 on one date. This tiny selected sample establishes neither stable reversion nor general profitability. The broader proxy loses, and source quote freshness remains unverified.

The peerbasket uses only past observations with a freshness bound and a minimum peer count. Tests check absent peers, opposite variant directions, and independence of previous decisions from future peer observations. Timestamp and numeric signal boundaries are checked by the common runner. Formulas and primary sources are in [the track README](C:/Users/prajw/Downloads/Trader/research/05_relative_value/README.md).

Preserved results are [comparison.csv](C:/Users/prajw/Downloads/Trader/research/05_relative_value/runs/initial-v1/comparison.csv) and immutable plans/source snapshots below that run. The fixed cohort is small and contains varied industries, so this basket is not a sector or official-market residual. Investigate synchronized reference-index and sector exposures on longer verified data before choosing another residual model. No thresholds were optimized from these results.
