# September 9 admission audit

The main reason good signals missed AI was occupied account capacity. Of 659
workflows, 417 hit five occupied trade slots and 114 hit analysis reservations.
There were 35 actual model runs. Admission uses arrival order and a per-account
lock, with no comparison against other candidates. This audit adds no queue.

## Occupancy evidence

The ordinary broker order book shows M Tek Copper's unfilled short cancelled at
15:10:28, after submission at 10:01:31. It occupied a slot for 308.95 minutes.
Jaykay's unfilled short ran from 11:57:11 to the same cancellation time, 193.28
minutes. Super Order timestamps retain the original creation time, so using only
that book hides how long these entries waited.

M Tek Copper was pending during 406 of the 417 capacity-blocked signals. Jaykay
was pending during 251. Pashupati's filled position was open during 415.
These counts overlap. After 13:23, the five occupied instruments were generally
Pashupati, Excelsoft, TCC, M Tek Copper and Jaykay. Two were unfilled entries.

Filled positions plus submitted entries reconstruct five slots at 416 of 417
blocked signal timestamps. The exception is 10:01:28, three seconds before the
M Tek Copper submission. Signal creation precedes admission, so this is compatible
with concurrent placement. No false-cap bug is demonstrated by these records.
Cancellation and submission timestamps establish intervals, not every broker
state transition inside them.

Examples of missed movement include Texmo Pipes at 11:13:15, rank 1, with a 6.28%
five-minute return; Mangalam Global at 12:25:54, rank 1, with 3.51%; both hit trade
capacity. Rasi Electrodes at 10:14:05, rank 8, rose 3.64% while analysis slots were
occupied. Goa Carbon at 09:26:49, rank 4, fell 3.30% with analysis capacity occupied.
These are retrospective price movements, not executable returns.

## Selection and delay

AI-run signals had median five-minute range 1.193% and absolute return 0.459%.
Trade-capacity-blocked signals had 0.794% and 0.368%; analysis-capacity-blocked
signals had 0.992% and 0.477%. Median rank was 6 for all three groups. The data
does not establish that admitted signals generally had less subsequent movement.
The visible misses are real, but choosing them retrospectively overstates what
was knowable at admission.

Median signal-to-preparation delay was 1.73 seconds, preparation-to-native-model
start 24.27 seconds, and model duration 97.21 seconds. The 35 runs comprised 15
gap rejections, 14 VWAP reversions, four opening-range acceptances and two
volatility ignitions. Twenty-one runs occurred before 10:00, six in the 10:00
hour, five at 11:00, two at 12:00, one at 13:00 and none after 14:00.

## Changes

Admission diagnostics now record the broker observation time, open-position
count, instruments with active orders, submission reservations, analysis
reservations, occupied instruments and deduplicated pending entry parents with
broker creation times and observed ages. Pending child exits do not appear as
waiting entry parents. Missing times produce an unknown age. These records use
the already fetched account data and preserve every admission decision.

Focused tests passed: 46 tests and 10 subtests across independent execution and
stock toolkits. No broker calls, live order changes, capacity increases or
automatic cancellations were made.

Next investigate explicit pending-entry validity and order lifecycle management.
A stale resting entry needs a broker-aware cancellation policy and cancellation
confirmation before capacity can be released. Silently ignoring it in capacity
counts could allow an unexpected later fill to exceed the account limit.

Sources: local session audit evidence.json, broker-refreshed.json, the report's
data.json, and current execution/orchestrator code. No account identifiers are
included in this document.
