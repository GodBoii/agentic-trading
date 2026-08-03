# Beginner’s guide to Dhan instruments, NSE/BSE, surveillance, and the trading pipeline

Last verified: 30 July 2026

This guide explains the system from first principles. It is educational material, not a promise that a filter will make money. A technically correct scanner can still lose money, so every strategy needs paper trading, realistic costs, risk limits, and ongoing measurement.

## 1. The four instrument fields are a hierarchy

Consider:

```text
EXCH_ID == "BSE"
SEGMENT == "E"
INSTRUMENT == "EQUITY"
INSTRUMENT_TYPE == "ES"
```

This reads like an address:

1. `EXCH_ID = BSE`: the marketplace is BSE Limited.
2. `SEGMENT = E`: look inside its equity/cash-market section.
3. `INSTRUMENT = EQUITY`: the broad exchange-defined instrument is equity.
4. `INSTRUMENT_TYPE = ES`: the more specific exchange subtype is an equity share.

The four conditions do not mean the same thing. Each condition narrows the previous one.

### EXCH_ID: which exchange?

The current Dhan detailed master contains:

| Value | Meaning | What normally trades there |
|---|---|---|
| `NSE` | National Stock Exchange of India | Shares, indices, stock/index derivatives, currency products and other instruments |
| `BSE` | BSE Limited, formerly Bombay Stock Exchange | Shares, indices, stock/index derivatives, currency products, debt and other instruments |
| `MCX` | Multi Commodity Exchange of India | Commodity futures and options, such as metals and energy contracts |

For ordinary Indian company shares, NSE and BSE are the two important venues in Dhan’s master. MCX is not another venue for Reliance or TCS shares; it is primarily a commodity-derivatives exchange.

India also has Metropolitan Stock Exchange of India (`MSEI`), and there are international exchanges in GIFT City. However, Dhan’s domestic instrument master documented here exposes `NSE`, `BSE`, and `MCX`. A system must not invent an `MSEI` Dhan exchange code unless Dhan explicitly supports it.

### SEGMENT: which department of the exchange?

The current master contains:

| Value | Full meaning | Simple explanation |
|---|---|---|
| `E` | Equity/cash segment | Actual shares and share-like securities bought in the cash market |
| `D` | Derivatives segment | Futures and options whose value comes from an underlying stock or index |
| `C` | Currency segment | Currency futures and options |
| `M` | Commodity segment | Commodity futures and options |
| `I` | Index segment | Index values such as NIFTY 50 or SENSEX; an index is a calculated number, not a company share |

The API-facing exchange-segment name is not always a direct concatenation of these letters. Examples are `NSE_EQ`, `BSE_EQ`, `NSE_FNO`, `BSE_FNO`, `NSE_CURRENCY`, `BSE_CURRENCY`, `MCX_COMM`, and `IDX_I`. Always use Dhan’s annexure mapping.

### INSTRUMENT: what financial contract is it?

The current master contains these broad instruments:

| Value | Meaning |
|---|---|
| `EQUITY` | Cash-market security, including several subtypes—not only normal company shares |
| `INDEX` | A calculated market index |
| `FUTSTK` | Future on an individual stock |
| `OPTSTK` | Option on an individual stock |
| `FUTIDX` | Future on an index |
| `OPTIDX` | Option on an index |
| `FUTCUR` | Currency future |
| `OPTCUR` | Currency option |
| `FUTCOM` | Commodity future |
| `OPTFUT` | Option on a commodity futures contract |

A future is an expiring contract whose price follows an underlying asset. An option gives its buyer a right, but not an obligation, to buy or sell according to its contract terms. These are leveraged products and can produce losses much faster than ordinary shares.

### INSTRUMENT_TYPE: what exact subtype did the exchange assign?

The current local Dhan master contains 28 distinct values. They fall into understandable families:

| Family | Values seen | Plain-English meaning |
|---|---|---|
| Ordinary/share-like equity | `ES`, `ETF`, `REIT`, `InvITU`, `MF` | Equity share, exchange-traded fund, real-estate investment trust unit, infrastructure investment trust unit, mutual-fund instrument |
| Debt/fixed income | `CB`, `DBT`, `DEB`, `GB`, `TB`, `PTC`, `PN`, `PS`, `Other` | Corporate bond/debt, debenture, government bond, treasury bill, pass-through certificate and other exchange-defined debt/security types |
| Index | `INDEX` | An index value |
| Futures | `FUT`, `FUTSTK`, `FUTIDX`, `FUTCUR`, `FUTCOM` | Generic, stock, index, currency, and commodity futures |
| Options | `OP`, `CUR OP`, `OPTSTK`, `OPTIDX`, `OPTCUR`, `OPTFUT` | Generic, currency, stock, index, currency, and futures/commodity options |

`ES` is therefore important: it distinguishes a company equity share from an ETF, bond, mutual fund, REIT, or other security that also happens to live in the exchange’s broad equity/cash segment.

Some abbreviations in this exchange-owned field are poorly documented or can change. The application should treat the values as classification codes, keep an allow-list for the specific strategy, and retain unknown values for review rather than guessing.

## 2. SERIES is another essential filter

Even `BSE + E + EQUITY + ES` is not enough. The `SERIES` or group describes how that share trades.

Common NSE examples include:

- `EQ`: normal rolling-settlement equity. This is the preferred NSE series for this scanner.
- `BE`: trade-to-trade surveillance series. Every purchase and sale creates delivery obligations; intraday netting is not allowed.
- `SM` and `ST`: small and medium enterprise series with different trading/settlement characteristics.
- `BZ` and `SZ`: special/surveillance or non-compliant categories that should not silently enter a normal intraday universe.

Common BSE examples include:

- `A`, `B`, and `X`: ordinary BSE equity groups of differing liquidity/market characteristics. The new universe permits these and lets historical liquidity filters decide.
- `T`, `XT`, `MT`, and `TS`: trade-to-trade groups. They are unsuitable for the intended normal intraday scan.
- `M` and related groups: small and medium enterprise securities.
- `Z` and `ZP`: companies with important listing/compliance concerns.
- `NS` and `NT`: records present in Dhan’s master that were responsible for hundreds of failed `BSE_EQ` lookups in the earlier scan. They must not be assumed to be normal supported BSE quotes.

Series meanings and membership can change. The exchange’s current specification remains authoritative.

## 3. Why deduplicate by ISIN and choose a venue?

### The problem

The same company can trade on both NSE and BSE. Each exchange gives it a different security identifier.

Reliance Industries in the current master is a useful example:

| Identity | NSE listing | BSE listing |
|---|---|---|
| ISIN | `INE002A01018` | `INE002A01018` |
| Dhan/exchange security ID | `2885` | `500325` |
| Exchange segment | `NSE_EQ` | `BSE_EQ` |
| Series | `EQ` | `A` |

The identical ISIN tells us these listings represent the same security. The exchange security IDs are only venue-specific addresses.

If the program stores only `500325` and hardcodes `BSE_EQ`, it cannot safely switch to NSE. If it sends `2885` with `BSE_EQ`, Dhan looks for BSE security 2885, not NSE Reliance. The request can fail or refer to an unrelated instrument.

### The better data model

Represent the company/security once:

```json
{
  "isin": "INE002A01018",
  "preferred_venue": {
    "exchange_segment": "NSE_EQ",
    "security_id": 2885
  },
  "available_venues": [
    {"exchange_segment": "NSE_EQ", "security_id": 2885},
    {"exchange_segment": "BSE_EQ", "security_id": 500325}
  ]
}
```

Then:

1. Group master rows by ISIN.
2. Prefer an ordinary supported NSE `EQ` listing.
3. If none exists, use a supported BSE `A`, `B`, or `X` listing.
4. Store both `exchange_segment` and `security_id`.
5. Pass that pair together to every quote, history, WebSocket, and order API.

“Prefer the most liquid venue” ideally means comparing recent traded value and bid-ask spread on both venues. The initial implementation uses NSE `EQ` as a practical default because it is commonly the more liquid venue, then Stage 1 and Stage 2 measure actual liquidity. A future enhancement can measure both venues and change the preference when BSE is demonstrably better.

The generated universe currently has 3,388 unique ISINs: 2,078 use NSE and 1,310 use BSE fallback listings. This is not a promise that all 3,388 are tradable; Stage 1 still removes illiquid and unsuitable stocks.

## 4. ASM and GSM in simple words

`ASM` means Additional Surveillance Measure. Exchanges apply it when objective trading behaviour—such as unusual price/volume movement, volatility, delivery percentage, or client concentration—deserves extra caution.

`GSM` means Graded Surveillance Measure. It focuses more heavily on cases where market price appears out of proportion to financial health or fundamentals. “Graded” means restrictions become stricter at higher stages.

These labels are warnings and controls, not court judgments that a company committed fraud.

Possible restrictions include higher margin, a narrow price band, trade-to-trade settlement, an additional cash surveillance deposit, trading only once per week, or no upward price movement at the strictest GSM stage.

### Do NSE and BSE both publish them?

Yes. SEBI’s surveillance directory officially links:

- NSE ASM and GSM reports.
- BSE ASM and GSM reports.
- MSEI ASM and GSM pages.

ASM is designed jointly by SEBI and exchanges and is applied uniformly at a market framework level, but identifiers and publication formats are exchange-specific. Match cross-exchange records by ISIN or another verified identity, never by assuming an NSE symbol equals a BSE code.

### A robust multi-source ingestion design

Use independent sources with provenance:

1. **NSE official report and circular attachments** for NSE-listed instruments.
2. **BSE official dashboard/download and circular attachments** for BSE-listed instruments.
3. **Dhan’s daily detailed master** as the broker-normalized `ASM_GSM_FLAG` and category view.
4. **The other exchange’s official list matched by ISIN** as a cross-check when a company is dual-listed.
5. **MSEI official data** only for MSEI instruments or corroboration; it is not a replacement for a missing NSE/BSE file.

The sequence should be:

```text
download -> validate format -> parse -> normalize by ISIN/venue ->
compare sources -> save source timestamps -> publish current snapshot
```

Validation is crucial. An HTTP 200 response can still be an HTML error page. Check file signature, required columns, row count, effective date, duplicate rate, and whether the data changed implausibly.

If sources disagree, do not silently overwrite one with another. Store the disagreement. For a conservative trading filter, the system may temporarily exclude the union of current official warnings while it alerts the operator, but this can over-exclude stocks.

Only after all current-source attempts fail should the system use the last-known-good snapshot. That snapshot needs:

- `effective_date`
- `downloaded_at`
- `source`
- checksum
- age in days
- a visible `stale=true` warning
- a maximum allowed age

The current project has BSE GSM download plus local-cache fallback and Dhan master flags. It does not yet have a fully validated NSE/BSE circular-attachment aggregator. That should be completed before claiming four interchangeable production feeds.

## 5. Compact and detailed instrument files

An instrument master is an address book. It tells the application how to refer to a share, future, option, index, bond, or fund in an API call.

### Compact-file fields

| Field | Meaning and use |
|---|---|
| Exchange | NSE, BSE, or MCX—the marketplace |
| Segment | Equity, derivatives, currency, commodity, or index department |
| Security ID | Venue-specific numerical address required by Dhan requests |
| Instrument name | Broad contract class such as equity, stock future, or index option |
| Expiry code | Compact contract-expiry representation used for derivatives |
| Trading symbol | Exchange’s short tradable symbol |
| Lot size | Minimum contract multiple. One options “lot” can represent many units |
| Display/custom name | Human-friendly name for screens and logs |
| Expiry date | Last valid date of a futures/options contract |
| Strike price | Price level written into an options contract |
| Option type | `CE` call or `PE` put |
| Tick size | Smallest legal price step, for example ₹0.05 |
| Expiry flag | Weekly (`W`) or monthly (`M`) options expiry |
| Exchange instrument type | More specific exchange subtype |
| Series | Trading/settlement group such as NSE `EQ` |
| Symbol name | Longer standardized instrument/company name |

This is sufficient when the program already knows what it wants and only needs the API address.

### Detailed-file additions

| Field | Meaning and use |
|---|---|
| ISIN | International Securities Identification Number: stable cross-venue identity for the same security |
| Underlying security ID/symbol | The stock/index/contract from which a derivative gets its value |
| Instrument type | More specific subtype such as equity share, ETF, bond, future, or option |
| Series/group | Exchange trading and settlement category |
| Bracket-order eligibility | Whether a bracket order is allowed. A bracket combines entry, profit target, and stop-loss legs |
| Cover-order eligibility | Whether a cover order is allowed. A cover order combines an entry with a compulsory stop-loss |
| ASM/GSM flag | Broker master’s current surveillance marker |
| Surveillance category | Stage/category associated with the surveillance flag |
| Buy/sell indicator | Whether the exchange/broker permits both sides or has restrictions |
| Cover/bracket margin and range settings | Minimum margin and allowed stop/target distance for those order types |
| MTF leverage | Margin Trading Facility leverage allowed for eligible delivery positions; borrowed funding increases both gain and loss |
| Upper circuit | Highest price the security is allowed to trade at during the applicable session/band |
| Lower circuit | Lowest allowed price |
| Freeze quantity | Maximum quantity accepted in one order before the exchange requires smaller/sliced orders |

The detailed file is better for universe construction because it answers not only “what is its ID?” but also “what is it, how may it trade, and is it under surveillance?”

### Data-quality cautions

Derivative rows can remain in the file after expiry. Filter them by instrument, expiry date, and active contract rules.

CSV exports may contain a final empty unnamed column. Ignore only columns whose names and contents are empty; do not delete arbitrary unknown columns. Validate the required named columns before publishing the master.

Flags can have undocumented values. Dhan documents `N`, `R`, and `Y` for ASM/GSM, while the current local file also contains a small number of `P` values. Preserve and alert on unknown values instead of interpreting them without confirmation.

## 6. What Stage 1 should do

Stage 1 answers:

> “Based only on completed past sessions and static safety information, which shares are worth watching today?”

It should run before the live decision stage and should not let today’s partial market action contaminate its baseline.

The corrected project flow is:

1. Load the latest Dhan detailed master.
2. Keep supported ordinary NSE/BSE equity shares.
3. Deduplicate by ISIN and choose a venue.
4. Exclude current ASM/GSM instruments.
5. Fetch completed daily historical candles.
6. Require at least 21 valid daily sessions.
7. Calculate historical close price, average traded value, average volume, volatility, prior-session range and return.
8. Apply the historical filters.
9. Save passed stocks and a reasoned summary under `python-backend/results/stage1/`.

Stage 1 previously called Dhan’s live OHLC snapshot only to get `last_price`. That created hundreds of “missing OHLC” exclusions before historical data was attempted. It also contradicted the historical-only design. The corrected implementation makes zero live OHLC snapshot calls in Stage 1 and derives price from the latest completed daily candle.

### OHLCV

`OHLCV` means:

- Open: first traded price in the candle.
- High: highest traded price.
- Low: lowest traded price.
- Close: final traded price.
- Volume: number of units traded.

A daily candle summarizes one session. A one-minute candle summarizes one minute.

### ADV20

`ADV20` in this project means 20-session Average Daily **Traded Value**, despite the common ambiguity of “average daily volume.”

For each day:

```text
traded value = closing price × volume
```

Then:

```text
ADV20 = average of the last 20 daily traded values
```

Dividing rupees by 10,000,000 expresses the answer in crore rupees.

Example: if a stock typically trades 1,000,000 shares per day around ₹200, its daily traded value is roughly ₹20 crore. A higher traded value usually means it is easier to enter or exit without moving the price, though bid-ask spread and depth must still be checked live.

### ATR%

`ATR` means Average True Range. It estimates normal daily movement while accounting for gaps from the previous close. `ATR%` divides ATR by the current price, allowing comparison between a ₹100 share and a ₹3,000 share.

An ATR% of 2% roughly says the stock’s recent daily range has been around 2% of its price. It measures movement, not direction.

## 7. Why 14 candles were not enough

The former logic did two inconsistent things:

1. It allowed a stock with only 14 daily candles.
2. It calculated a field named `adv_20_cr` with `tail(20)`.

In pandas, `tail(20)` does not require 20 rows. If only 14 exist, it quietly uses 14. The resulting number was a 14-day average wearing a 20-day label.

Suppose:

```text
Stock A has 20 valid sessions -> genuine ADV20
Stock B has 14 valid sessions -> 14-session average mislabeled ADV20
```

Those numbers are not directly comparable.

The new minimum is 21 sessions:

- 20 completed sessions for genuine ADV20.
- One additional prior session for return/previous-close comparisons.

An insufficient-history stock is not an API failure. It may be a new listing, a rarely traded security, or a row with sparse valid data.

The reporting categories must be separate:

- `failed_fetch`: request failed or no usable response arrived.
- `insufficient_history_count`: data arrived successfully, but fewer than 21 valid sessions existed.
- `filtered`: enough data arrived, but the stock failed price/liquidity/volatility rules.
- `passed`: enough data arrived and every Stage 1 rule passed.

This distinction matters operationally. A high API-failure rate means infrastructure is unhealthy. A high insufficient-history count describes the universe, not the network.

## 8. What Stage 2 does

Stage 2 answers:

> “Among the historically acceptable shares, which ones show unusual, tradable activity right now?”

The current implementation uses two live/current-day mechanisms:

1. A batched Dhan quote snapshot for price, bid, ask, spread, volume, depth, and related fields.
2. Dhan intraday one-minute history including today’s developing candles and earlier comparison days.

It computes:

- time-of-day Relative Volume
- Volume-Weighted Average Price
- opening-range breakout
- recent volume acceleration
- bid-ask spread and live liquidity quality

This is live-stage logic even though one input arrives through an intraday-history API. The word “historical” in the endpoint name does not mean the returned current-day candles are a completed historical baseline.

A WebSocket tick collector can make the live layer faster and more precise by continuously updating data. REST quote snapshots and intraday candles are still useful for periodic scans and recovery. Stage 2 should consume the freshest validated source and record its timestamp.

## 9. RVOL explained completely

`RVOL` means Relative Volume. It asks:

> “Is this stock receiving more participation now than is normal for this same time of day?”

At 10:00 a.m., do not compare today’s 10:00 a.m. volume with an average full-day volume. That would compare 45 minutes with an entire session.

Use:

```text
time-of-day RVOL =
today's cumulative volume up to 10:00
/
average cumulative volume up to 10:00 on previous comparable days
```

Example:

```text
Average previous volume by 10:00 = 200,000 shares
Today's volume by 10:00          = 500,000 shares
RVOL                              = 2.5
```

RVOL 2.5 means participation is approximately 2.5 times normal. It does not say buy or sell. Price may be rising or falling, and the volume may be caused by news, a block trade, panic, or manipulation. Combine RVOL with direction, spread, VWAP, breakout quality, news, and risk controls.

## 10. Other Stage 2 terms

### VWAP

`VWAP` means Volume-Weighted Average Price. Prices where more shares traded receive more weight. Institutions often use it as an intraday reference.

Price above VWAP suggests buyers have kept price above the day’s volume-weighted average; price below suggests the opposite. Repeated crossing can indicate a directionless day.

### Opening range

The opening range is the high and low during the first chosen period, such as 15 minutes. A later break above the high can signal expansion, but false breakouts are common.

### Volume acceleration

Compare a recent volume window with the immediately preceding comparable window:

```text
last 5-minute volume / previous 5-minute volume
```

A value of 2 means the recent window traded twice the volume. Very large ratios need denominator safeguards because dividing by an almost-zero earlier volume produces a misleading spike.

### Bid, ask, and spread

The bid is the best displayed buying price. The ask is the best displayed selling price. Their difference is the spread.

If the bid is ₹100 and ask is ₹100.20, a market buyer pays around ₹100.20 while an immediate seller receives around ₹100. The ₹0.20 gap is a real trading cost and a liquidity warning.

## 11. A clearer stage architecture

The pipeline can be understood as:

```text
Stage 0 — Reference and safety data
instrument master, venue mapping, ISIN deduplication, ASM/GSM, holidays

Stage 1 — Completed historical baseline
price, liquidity, volatility, prior-session behaviour, data sufficiency

Stage 2 — Live momentum and participation
RVOL, VWAP, opening range, acceleration, quote and spread

Stage 3 — Execution-quality gate
fresh depth, slippage estimate, circuit distance, position size, risk limits

Stage 4 — Agent analysis and controlled execution
charts, evidence, regime, final decision, order validation, audit log
```

Adding stages is useful only when each stage has a clear responsibility. Splitting one calculation into many numbered stages without reducing API work or clarifying failure handling adds complexity rather than efficiency.

## 12. Result folders

The project now separates primary outputs:

```text
python-backend/results/
  stage1/
    latest.json
    YYYY-MM-DD.json
    YYYY-MM-DD-degraded.json
  stage2/
    latest.json
    YYYY-MM-DD.json
    tick-stats-YYYY-MM-DD.json
    tick-history-YYYY-MM-DD.json
  monitor/
  regime/
  agents/
```

Each snapshot should include its generation time, market date, status, input count, exclusion counts, true failures, filter configuration, and source freshness. A degraded diagnostic file must not replace the last valid official snapshot.

## 13. Dhan WebSocket: 5,000 versus 100

These are two different limits:

- **5,000 instruments per connection** is the maximum active subscription capacity of one WebSocket connection.
- **100 instruments per JSON message** is the maximum batch size when asking that connection to add subscriptions.

Think of a bus:

- The bus can carry 5,000 passengers.
- Only 100 passengers may board through the gate in one group.

To subscribe 5,000 instruments on one connection, send 50 messages:

```text
message 1: instruments 1–100
message 2: instruments 101–200
...
message 50: instruments 4,901–5,000
```

All 5,000 remain subscribed on the same connection. You do not need 50 connections.

Dhan documents up to five WebSocket connections per user, each with up to 5,000 instruments. That is a theoretical capacity of 25,000 active instrument subscriptions, subject to correct connection management and Dhan’s account/data-plan rules. More connections are not automatically faster or better. One well-managed connection for the Stage 2 universe is normally simpler.

The request messages are JSON, but Dhan sends market packets in binary for speed. The client must parse packet formats and respond to WebSocket ping/pong health checks.

## 14. Access-token renewal

There are two different use cases.

### Backend scanner account

Dhan documents `RenewToken` for an active token generated from Dhan Web. Renewal:

1. Must happen before the current token expires.
2. Invalidates the old token.
3. Returns a new token valid for another 24 hours.

The project now has a `dhan-token-renewer` backend service. It checks the profile periodically, renews near expiry, and atomically writes a shared runtime credential. Long-running Dhan services detect the changed file and rebuild their API clients, avoiding the false assumption that Docker rereads `.env`.

If the token has already expired, renewal fails. The system must alert early enough for manual recovery.

### Website users connecting their own Dhan accounts

Dhan explicitly documents `RenewToken` as working only for Dhan-Web-generated tokens. A token obtained from the API-key OAuth consent flow must not be assumed renewable through the same endpoint.

For a platform serving multiple users, use Dhan’s supported Partner integration and lifecycle. Do not store users’ PINs or Time-based One-Time Password secrets as an improvised refresh-token system.

Tokens must be encrypted at rest, excluded from logs, scoped to the correct user, monitored for expiry, and never sent to the browser unless Dhan’s supported flow explicitly requires it.

## 15. Official references

- [Dhan instrument list](https://dhanhq.co/docs/v2/instruments/)
- [Dhan live market feed](https://dhanhq.co/docs/v2/live-market-feed/)
- [Dhan authentication and renewal](https://dhanhq.co/docs/v2/authentication/)
- [Dhan market quote API](https://dhanhq.co/docs/v2/market-quote/)
- [SEBI surveillance source directory](https://www.sebi.gov.in/curation/surviellance.html)
- [NSE Additional Surveillance Measure](https://www.nseindia.com/static/regulations/additional-surveillance-measure)
- [NSE Graded Surveillance Measure](https://www.nseindia.com/static/regulations/graded-surveillance-measure)
- [NSE ASM reports](https://www.nseindia.com/reports/asm)
- [NSE GSM reports](https://www.nseindia.com/reports/gsm)
- [BSE ASM reports](https://www.bseindia.com/markets/equity/EQReports/additional_surveillance_measure.aspx)
- [BSE GSM reports](https://www.bseindia.com/markets/equity/EQReports/graded_surveil_measure.aspx)
