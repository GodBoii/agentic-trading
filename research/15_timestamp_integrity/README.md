# Timestamp integrity and raw depth research

This is an offline recording-contract study. It improves the evidence available to later replay experiments without claiming a trading edge. The code reads archived Parquet files and never connects to a feed, broker or credentials.

## Sources and the timestamp ambiguity

- [Dhan's official live feed protocol](https://dhanhq.co/docs/v2/live-market-feed/) describes full-response code eight, last-trade time as epoch seconds, little-endian messages and five twenty-byte bid/ask depth structures. Its listed full packet does not supply a quote event timestamp or exchange sequence number. Last-trade time is therefore not a timestamp of the accompanying order book.
- [The official Python SDK source](https://github.com/dhan-oss/DhanHQ-py/blob/main/src/dhanhq/marketfeed.py) decodes full packets with `<BHBIfHIfIIIIIIffff100s` and depth levels with `<IIHHff`. The reviewed current `utc_time` function converts epoch seconds with `datetime.fromtimestamp(epoch_time, timezone.utc)` and then formats only `%H:%M:%S`. That output loses the date and explicit timezone. The archived decoder version is unknown, and the raw-depth files contain decoded JSON rather than original binary bytes. Current SDK semantics cannot prove the historical token's semantics.

The earlier lab auditor attached bare trade clocks to the receipt's local date. That is now explicitly one arithmetic sensitivity, not normalized source truth. This track also computes a same-date UTC sensitivity. A different timezone changes the offset by 19,800 seconds on these daytime receipts. Choosing the smaller offset would create a false freshness guarantee.

## Normalized contract

`normalizer.py` creates frozen records with venue identity, receipt token and UTC microseconds, raw last-trade token, parsed clock text, absolute trade epoch where explicitly available, signed receipt-minus-trade arithmetic where defined, capture scope, decoder provenance, market levels and input hash.

Bare clocks retain unknown absolute trade date/timezone. Quote event timestamp, source quote age and exchange sequence remain unknown even for valid binary full packets. Negative explicit trade offsets stay negative. A valid book is not a freshness certificate or proof of a future executable fill.

Best-level quantities and five-level summed quantities have separate fields. Prices must be ordered, numeric and positive, and the best book must not cross. Malformed venue/identity, timestamp, depth or JSON fails closed with an error code. Unknown capture scope stays unknown rather than becoming complete capture.

`normalize_binary_full` is an offline adapter for a future archived full wire packet. It checks code, size, venue, security and depth, preserves the integer trade epoch and original byte hash. Synthetic binary tests establish the parser behavior. No original wire bytes exist in the sampled archive, so this adapter does not restore them.

## Audit and reproduction

Frozen questions are in `hypotheses.md`. The audit uses the prior August 18 twelve-stock ADV cohort and reads up to 20,000 selected NSE cash packets per date in sorted file order for August 28, August 31 and September 1. It preserves source file hashes, row positions, capture scope, normalized hashes, validation failures, time sensitivities and aggregate-to-best depth ratios. It does not assume independent samples or representative full-day coverage.

Run `python -m unittest discover -s research/15_timestamp_integrity/tests -v` and `python -m research.15_timestamp_integrity.run` from the repository root. Existing run directories are preserved; a repeated invocation fails instead of overwriting evidence. See `runs/initial-v1/plan.json`, `audit.json` and normalized JSONL files.

The correct next recorder preserves original binary bytes, explicit wire last-trade epoch, decoder version/source hash, UTC wall receipt and monotonic receipt clocks, predefined capture cohort and scope, reconnect/session identifiers, local receive sequence, parser failures and queue drops. Those fields provide traceability; they still cannot invent an exchange quote timestamp that the feed does not supply. Record source clock synchronization evidence separately.
