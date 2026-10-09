# One-minute forecasts transferred to options

All 18 fixed configurations use 1655 chronological out-of-sample forecast rows on 9 previously viewed dates. Nearby depth and the one-minute horizon were selected after study02. This is development research.

Thresholds of 0.5, 1 and 2 bps are registered together. No best threshold is promoted. Price-only, price plus nearby depth and momentum each select a long option or a 50-point debit spread. Contracts are selected at decision time, priced after one second and closed 60 seconds after the decision using the same identities. The 59-second exposure interval ends at the underlying one-minute forecast label. Zero forecasts produce no trades and zero costs.

| Policy | Threshold bps | Structure | Entered | Priced / unknown | Gross INR | Charges INR | Net INR | Stressed net INR |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| price | 0.5 | single | 4 | 4 / 0 | -832.00 | 259.63 | -1143.63 | -1351.63 |
| price | 0.5 | vertical | 3 | 3 / 0 | -211.25 | 383.63 | -672.88 | -984.88 |
| price | 1 | single | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| price | 1 | vertical | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| price | 2 | single | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| price | 2 | vertical | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| price_near | 0.5 | single | 152 | 152 / 0 | 87.75 | 9577.59 | -11465.84 | -19369.84 |
| price_near | 0.5 | vertical | 144 | 144 / 0 | -2795.00 | 17591.96 | -24130.96 | -39106.96 |
| price_near | 1 | single | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| price_near | 1 | vertical | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| price_near | 2 | single | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| price_near | 2 | vertical | 0 | 0 / 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| momentum | 0.5 | single | 1084 | 1084 / 0 | -5739.50 | 65943.02 | -85774.52 | -142142.52 |
| momentum | 0.5 | vertical | 945 | 945 / 0 | -16812.25 | 111042.09 | -152424.34 | -250704.34 |
| momentum | 1 | single | 687 | 687 / 0 | -2145.00 | 41907.33 | -52983.33 | -88707.33 |
| momentum | 1 | vertical | 600 | 600 / 0 | -9811.75 | 70747.38 | -96159.13 | -158559.13 |
| momentum | 2 | single | 254 | 254 / 0 | -120.25 | 15456.17 | -18878.42 | -32086.42 |
| momentum | 2 | vertical | 222 | 222 / 0 | -3276.00 | 26150.44 | -35198.44 | -58286.44 |

Gross already uses ask for buys and bid for sells. Charges include estimated brokerage, exchange/IPFT, SEBI, GST, sale-premium STT and buy-side stamp duty. Net also subtracts 0.10 points per unit per transaction; the stressed column uses 0.50. The half-spread diagnostic is saved separately and is never deducted a second time.

Unknown exits remain open in the conditional ledger and block re-entry for the rest of that date. Their final P&L and full costs are unknown. Therefore each net figure covers the priced subset only, even when positive. Blocked, missing-candidate, missing-entry and no-signal counts plus date outcomes are in results.json.

The input forecast file also omits decisions without known future underlying labels. This coverage selection existed before option replay. A subsequent prospective collector must preserve every causal prediction, including missing outcomes.

A smaller forecast error need not produce option profit. Option movement, bid/ask spread, order count and charges decide economic transfer. Different policies take different schedules and contracts, so subtracting their net totals does not establish a causal nearby-depth benefit. No trade is the zero-cost reference. No configuration is approved for trading.

Source definitions and fee references are in README.md. Input, dependency and study hashes are in results.json. Run `python research/11_one_minute_option_transfer/study.py` from nifty-research.
