# Intra-Finder v2 implementation record

## Production shape

- Broad tradable NSE/BSE universe, expected at 3,500 to 4,000 instruments.
- One Full Packet WebSocket connection.
- One-second opening ranks and five-second regular-session ranks.
- Top 60 working set, top 100 hysteresis reserve and top 10 setup admission.
- Explicit opening drive, gap rejection, opening-range acceptance, volatility
  ignition and VWAP reversion setup families.
- Five-minute per-stock, per-family re-arm interval.
- Configured concurrent new-entry agents and active-trade gate.
- Live event dispatch by default, with the shadow switch retained.

## August 28 causal replay

The August 28 recording starts at 10:19 IST, so it cannot test opening behavior.
It contains 3,781,457 raw Full Packets through 13:41.

The production ranker and setup engine were replayed at the regular-session
cadence using the normalized tape:

- 796,851 ten-second replay observations.
- 130 setup events.
- 37 unique stocks.
- 73 `VOLATILITY_IGNITION` events.
- 57 `VWAP_REVERSION` events.

An earlier top-20 replay produced 205 events across 56 stocks. Reducing setup
admission to the top 10 materially lowered traffic while preserving the complete
top-60 research tape.

These counts measure detector behavior, not profitability. A complete stable
session beginning before 09:15 is required to validate opening-drive and gap
setups.

## Performance

The 4,000-stock synthetic rank benchmark remains below the 500 ms regression
bound. After moving stale-state rejection ahead of rolling-feature calculation,
the September 1 live 3,535-stock rank measured 209 ms after warm-up.
The live path performs no REST calls, Pandas operations, chart generation,
agent HTTP waits or disk writes.
