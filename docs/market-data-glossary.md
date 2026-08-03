# Market Data Glossary

## Identity

**Exchange** is the venue, such as NSE or BSE.  
**Segment** is the market section, such as cash equities.  
**Security ID** is Dhan's address for one instrument on one venue.  
**ISIN** is the cross-exchange identity of the underlying security.  
**Series/group** is an exchange classification such as NSE `EQ` or BSE `A`.

The security ID alone is not a complete address. The system always carries
`exchange_segment + security_id`.

## Instrument master files

The compact master mainly contains fields needed to address instruments. The
detailed master adds ISIN, series/group, surveillance, trading permissions,
margin attributes, circuit levels and other tradability information. Universe
Scanner therefore uses the detailed master.

**ASM/GSM** are surveillance frameworks for securities requiring extra caution.
Dhan combines them in one flag. This system only needs an exclusion decision, so
every flagged ordinary equity is removed.

## Price and volume

**OHLC** means open, high, low and close.  
**Volume** is how many shares traded.  
**Traded value** is approximately close price multiplied by volume.  
**ADV20** is average traded value over exactly twenty sessions.  
**ATR** estimates typical price range, including gaps.  
**RVOL** compares today's volume so far with normal volume at the same time.

An RVOL of 1.5 means approximately 50% more activity than normal at that time.

## Live order book

**Bid** is a standing buy price.  
**Ask** is a standing sell price.  
**Spread** is the distance between best ask and best bid.  
**Depth** is the quantity available at several bid/ask levels.  
**Imbalance** compares total bid quantity with ask quantity.  
**Slippage** is the difference between the visible reference price and the
average price expected when an order consumes available levels.

A large displayed bid is supporting evidence, not certainty. Orders can be
cancelled, so setup rules combine depth with price and executed volume.

## Intraday structures

**VWAP** is the session's volume-weighted average price. It approximates the
average price paid per share.  
**Opening range** is this system's 09:15–09:30 high/low.  
**ORB** is a confirmed break outside that range.  
**Volume acceleration** asks whether recent activity is faster than the previous
few minutes.

No single indicator is a complete trade setup. Intra-Finder combines structure,
participation, depth, capacity and data quality.
