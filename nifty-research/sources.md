# Data and cost sources

Reviewed 30 September 2026. Broker documentation can change; data availability in documentation does not establish archive completeness.

- [Dhan Full market feed](https://dhanhq.co/docs/v2/live-market-feed/). Latest trade, cumulative volume, OI and five-level quotes.
- [Dhan 20/200-level depth](https://dhanhq.co/docs/v2/full-market-depth/). Aggregated price-level quantities, one instrument per 200-depth connection.
- [Dhan option chain](https://dhanhq.co/docs/v2/option-chain/). IV, Greeks, OI and top bid/ask sizes; those richer fields are absent from the normalized option archive.
- [Dhan rolling expired options](https://dhanhq.co/docs/v2/expired-options-data/). Preserve actual strikes when reconstructing fixed positions from rolling ATM-relative data.
- [NSE STT schedule](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax). Option-sale STT of 0.15% from 1 April 2026.
- [Dhan pricing](https://dhan.co/pricing/). F&O brokerage of INR 20 per executed order, GST on applicable charges, SEBI turnover fee and stamp duty.
- [NSE transaction and IPFT revision](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf). From 1 March 2026, options transaction charge INR 3,552.99 and IPFT INR 0.01 per crore of premium turnover per side. Combined rate 0.0003553 of premium turnover. The primary circular differs from some summaries in how it splits those two items.
- [NSE Nifty lot revision](https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf). The archive's applicable contracts use 65 units. Live systems must resolve actual instrument metadata.
- [NSE retail algo FAQ](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf). Static IP, broker controls and API order tagging are future execution requirements.
- [Cont, Kukanov and Stoikov](https://arxiv.org/abs/1011.6402). Motivation for order-flow research; the study is not evidence of a profitable Nifty retail strategy.

Costs are continuous estimates. Actual contract-note rounding, expiry exercise taxes, brokerage for assignments and account-specific fees require reconciliation. The current replay closes before expiry settlement and does not simulate exercised options.
