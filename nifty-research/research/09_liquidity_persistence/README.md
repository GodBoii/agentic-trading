# Time-based near-price liquidity persistence

This study separates sustained near-price aggregate liquidity from recently observed liquidity and distant raw wall counts. It reparses four long recordings, August 3, 19, 20 and 21, approximately 7.31 GB of 200-depth NDJSON.

```powershell
python nifty-research/research/09_liquidity_persistence/study.py
python nifty-research/research/09_liquidity_persistence/study.py --reuse
python -m pytest --import-mode=importlib nifty-research/research/09_liquidity_persistence/test_study.py -q
```

The first command reads raw files and checks their hashes against study 01. The second reuses its ignored local seconds cache only after verifying parquet/audit digests, parser definitions, reader code, the baseline manifest and current source size/mtime. Missing provenance or actual packet timestamp columns requires a raw parse. Neither command calls a market API or changes raw archives.

## Evidence and transfer limits

- [Bechler and Ludkovski, Order flows and limit order book resiliency on the meso-scale](https://arxiv.org/abs/1708.02715). Their Nasdaq research motivates distinguishing passive flow, depth shape and resilience. This study cannot observe exact individual-order additions or cancellations and does not reproduce their event-level model.
- [Lo and Hall, Resiliency of the limit order book](https://www.sciencedirect.com/science/article/pii/S0165188915001797). The publisher abstract describes Australian-equity liquidity recovery after shocks. It motivates time-based measurements and separate near/deep book measures, but does not establish Nifty predictability. The accepted-manuscript download returned HTTP 429, so this reference uses the publisher abstract only.
- [mamonet/orderbook-heatmap](https://github.com/mamonet/orderbook-heatmap). Inspected its descriptions of absolute-price liquidity bands, depth sampling and clusters. Its documentation identifies synthetic screenshot generation. Images and setup scores are not empirical forecasting validation. No repository code was executed or copied.

Sources accessed October 1, 2026.

## Rules fixed before this run

At each integer-second boundary, use only packets captured strictly earlier. Both sides must be at most one second old, share the contract, have correctly ordered finite prices/sizes and be uncrossed. Missing valid grid samples restart presence measurements. Gaps longer than ten seconds, recorder sequence resets and contract changes reset the segment. Sampling is equal-time, so a burst of book updates does not create extra decision weight.

A qualifying level is within ten index points of midpoint and has at least 650 or 1,300 units. For each threshold, test continuously observed presence of 10, 30 or 60 seconds. A separate transient measure uses less than five seconds. Persistence refers to continuing aggregate size above the threshold at the same side/price. It cannot prove the same orders remain there, and cannot classify spoofing, institutional identity or cancellation versus execution.

```text
presence_age = current_second - first_consecutive_valid_second
persistent_side_size = sum(current size of qualifying levels with age >= duration)
persistent_imbalance = (persistent_bid_size - persistent_ask_size) / total
near_imbalance = (size within 10 points on bid - size within 10 points on ask) / total
deep_wall_count_imbalance = (bid levels >= 300 units - ask levels >= 300 units) / total count
signed_response_h = sign(signal_at_decision) * 10000 log(midpoint_at_t+h / midpoint_at_t)
```

The minutes require 55 of 60 valid grid samples, the first sample within two seconds of the opening boundary and the final grid within two seconds of decision time. The oldest packet making up the final book must also be within two seconds of decision time. Grid timestamps and actual packet timestamps remain separate. The last rule corrects an aggregation bug found October 2, without changing the hypothesis thresholds. History and labels must remain within one segment, with six complete history minutes and contiguous complete future minutes. Evaluate 1, 3 and 5 minutes. A signal activates when its absolute imbalance is at least 0.10. These thresholds are not optimised after looking at outcomes.

Six persistent signals, two transient signals and three control signals across three horizons create 33 response trials. For each persistent trial, compare all three controls on the exact same signal cohort, creating 54 paired comparisons. Raw cohort means are not directly comparable because eligible minutes differ. Daily sign-flip p-values receive Holm correction separately within those two families. Four dates give coarse uncertainty and do not validate a live strategy.

This is conditional response analysis on selected long-coverage dates, not a chronological fitted-model evaluation. It is useful for rejecting weak ideas and defining a prospective follow-up. It excludes fills, transaction costs, option IV and hedging. Read `artifacts/report.md` and `findings.md` for the actual outcomes.
