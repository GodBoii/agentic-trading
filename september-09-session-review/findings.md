# September 9, 2026 session findings

Read-only review of the completed market session. Broker snapshot: 16:03:09 IST.
All signal, AI-session and broker orders were matched by identifiers. The HTML
report contains charts for all 118 signalled stocks and an audit of every one of
the 26 AI-submitted Super Orders.

A final read-only recheck at **16:26:25 IST** still showed TCC BSE −9 and NSE +9,
with both BSE protective legs cancelled. The Forever Order list was empty.

## What happened

- 17,911,336 market packets; 660 signals; 659 account-workflow dispatches.
- 35 actual AI runs, confirmed against native Agno sessions in Supabase.
- 53 placement-tool calls. 27 stopped before submission, including 18 price-drift
  rejections, six invalidated setups and three stale quotes.
- 26 submitted Super Orders. 23 entries filled; Axtel was rejected, and the MCL
  short and Jaykay entries were cancelled without fills.
- 22 entries closed on the same venue: nine profitable and thirteen losing.
  Realized P&L reconciles to Dhan at **−₹24.17 before fees**. Open TCC positions
  are excluded from that figure; their reported combined unrealized P&L was
  −₹3.69 at the snapshot.

## Did the AI set TP and SL correctly?

**Yes at submission.** All 26 requests contained a target and stop, with the
correct side geometry. The initial response showed both protective legs pending.
The requested prices match all 26 broker Super Order records. All 23 filled
entries also lie between their initial target and stop.

**That does not establish continuous protection.** We do not have a complete
historical stream of leg activation, price modification, cancellation and fill
events. The end-of-day snapshot alone cannot identify who changed a leg or
exactly when protection stopped being effective.

### Graphite: stop configured, protective exit did not close the position

- Signal 09:15:58; AI run 09:16:46.
- BSE short submitted 09:18:05, filled 09:18:21 at ₹785, one share.
- Initial target ₹768 and SL ₹792 were confirmed.
- Recorded prices were already above ₹792 in the 09:19 minute.
- A linked BUY LIMIT child appears cancelled, at ₹789.25, with its last recorded
  update at 09:57:25. The record does not preserve its full earlier history.
- A separate BUY MARKET order filled at 09:57:25 at ₹863.60.
- Loss: **₹78.60**, versus ₹7 initial entry-to-stop distance for one share.

This is not a missing stop in the AI request. It is a failed protection/exit
outcome. The saved records do not prove whether a modification, a pending limit
exit, broker handling or another action caused the failure. The separate market
exit is not one of the AI placement-tool calls in this session.

### TCC: opposite exchanges are still separate positions

- BSE short: nine shares at ₹51.75, filled 13:23:15.
- Initial target ₹49.60, SL ₹52.50, trailing jump ₹0.25.
- Both BSE protective legs are cancelled. A linked BSE BUY LIMIT order at ₹50.80
  was cancelled at 15:12:10.
- An NSE market buy attempt for nine shares was rejected at 15:11:28. A later
  NSE BUY filled nine shares at ₹51.91 at 15:13:10.
- Dhan positions still report **BSE −9** and **NSE +9**, both intraday. The open
  positions were also visible in the user's dashboard.

The NSE buy is not a confirmed BSE close, and it is not linked to an AI order
tool call. At the snapshot, the original BSE short had no active Super Order SL.
There is no corresponding protective Super Order for the separate NSE buy in
the returned order books. These positions need broker/account reconciliation.
No trading action was performed during this review.

### Pashupati: position closed, protection still marked pending

- Short five at ₹81.40 at 09:32:34; target ₹80.50, SL ₹81.90.
- A separate market buy closed five shares at ₹81.13 at 15:11:29.
- Broker positions show zero net quantity, but both Super Order legs still say
  PENDING. Treat this as unresolved order-state reconciliation, not proof of an
  unprotected position or proof of live executable orphan orders.

### Normal cancellation versus failed protection

Twelve filled entries have a broker SL exit and linked filled child order. Eight
have a target exit and linked filled child order. The opposite leg's cancellation
after one exit fills is expected OCO behavior. A cancelled SL is therefore not
automatically a failure. [Dhan's execution explanation](https://dhan.co/support/orders-and-positions/super-orders-on-dhan/how-is-a-super-order-executed/)

Several linked stop-exit limit orders remained between recorded creation and
last update for minutes, including PCBL at 448 seconds and Manoj Vaibhav Gems at
393 seconds. Those are recorded order-lifecycle intervals, not proven trigger-to-
fill times. A stop trigger and a completed exit must be tracked separately.

## Scanner and latency findings

- The new daily event counter matches all 660 durable signal records.
- Longest armed-to-trigger confirmation was 11.58 seconds. The old hour-long
  armed timers did not recur in today's emitted events.
- The feed reconnected once around 14:27. Peak packet-processing delay was
  **12.04 seconds**; **18.90%** of packet observations waited above 250 ms.
  The run cannot be described as consistently low latency.
- Signal to actual AI-run creation: median **26.27 seconds**, maximum **79.04
  seconds**. Median signal-to-first-order-attempt was **100.36 seconds** among
  runs that attempted placement.
- 417 dispatches stopped because trade slots were full; 114 because analysis
  capacity was occupied. Those were not expensive AI runs.
- 64 late events were rejected by authorization/IP checks, beginning 14:28:01.
  The feed could continue while account-level order access was unavailable.
  The user reconnected after the session; refreshed read-only queries succeeded.
- The opening range was verified for 2,385 of 3,510 stocks. Recovery completed
  785 requests and failed 2,989 attempts, predominantly incomplete opening data.
- Today traded on the September 8 fallback universe. The morning scanner
  started at 07:00 but did not publish before the feed opened. Today's successful
  profile report was built after 15:30 and was not today's live input.
- Among 631 signals with usable five-minute follow-up, median subsequent price
  range was 0.874%; 49.6% ended in the detector's indicated direction. This
  describes movement, not achievable P&L or the independent AI's accuracy.

## What should change next

First reconcile TCC's venue-specific positions and Pashupati's pending-leg state.
Then implement and test an order-lifecycle monitor that links parent orders,
child orders, fills and same-venue net quantities. It must distinguish an armed
broker-side stop from a triggered but unfilled limit exit, cancelled protection,
and an unmatched close on another exchange. Define the escalation policy before
automating any replacement or emergency exit orders.

Keep a durable order-update timeline with modification and cancellation evidence.
Without it, a report can confirm the initial request and final result but cannot
prove continuous protection. Investigate the Graphite child order with the broker
using the saved order IDs. Do not add an unprotected entry fallback.

After the execution lifecycle is reliable, continue reducing chart/preparation
latency and checkpoint-related feed stalls, and repair morning profile publication.

## Screenshot labels

The green S symbol beside a name denotes a Super Order. SL is the stop-loss leg;
TG is the target leg, also called TP. The red S before the name means SELL; the
green B means BUY. Pending and zero filled quantity mean the order has not
executed. In the supplied screenshot, a BUY LIMIT stop-exit priced below the
current market, or SELL LIMIT stop-exit above it, may remain unfilled even after
the intended stop has been crossed. The screenshot is not used as dated evidence
for this September 9 report. [Super Order API](https://dhanhq.co/docs/v2/super-order/)

## Evidence and boundaries

Signals, decision archives and recorded prices came from Ubuntu. Actual AI start
times came from read-only Supabase session queries. Broker books were obtained
first through verified same-account runtime credentials, then independently
through the refreshed user connection. Initial and refreshed books agree on the
26 Super Orders, 52 orders and 48 fill records.

Raw evidence is kept in the ignored local research directory. The shareable HTML
excludes credentials and account identifiers. Charts use observed one-second
prices aggregated into minute candles, so intrasecond extremes may be absent.
Continuous protection, exact cancellation time and cancellation actor remain
unproven. The audit never treats a price touching a line as proof of a broker fill.

Verification: all 118 stock charts rendered in the browser; search, empty results,
protection filters, trade windows, 1m/5m candles and evidence links were exercised.
Mobile layout had no page-level horizontal overflow; charts and wide tables
scroll inside their own containers. Browser error logs were empty. Five focused
reconciliation tests and JavaScript syntax checks passed.
