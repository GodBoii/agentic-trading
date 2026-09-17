# Universe scanner correction, September 17

The implementation starts from `b15a633`, including the Intra-Finder reference
refresh fix. No ranking, setup, trade sizing, account authorization, or order
placement policy changes are included.

## Evidence

Production Stage 1 run reports show:

| Market date | Duration | Missing historical profiles |
| --- | ---: | ---: |
| September 3 | 45.3 minutes | 1,395 |
| September 7 | 37.1 minutes | 1,330 |
| September 8 | 26.0 minutes | 1,237 |
| September 9 | 6.2 minutes | 12 |
| September 10 | 8.7 minutes | 12 |
| September 11 | 80.9 minutes | 27 |
| September 15 | 83.2 minutes | 27 |

The September 16 build timed out during daily history. The September 17
verification report records all daily profiles processed, but only 1,500 of
3,520 baselines finished when the 90-minute guard killed the child.

The cache inventory still includes 1,715 baseline files generated September 10.
Their seven-day freshness period expires September 17. This supports increased
baseline refresh work that day; it does not measure its exact contribution to
the overrun. Failed runs retain successful individual cache updates.

The broad universe stayed near 3,500 stocks throughout this interval. A sudden
increase in universe size does not explain the slowdown. September 1 introduced
the scanner's ten-minute retry loop. September 9 added daily-profile fallback
recovery. These changes improve recovery but can expose long shared cooldowns.
Historical request-level error counts were not persisted, so the exact mix of
broker failures on September 16 cannot be reconstructed.

A reproduction using the deployed service confirmed that 12 input-error
responses open a five-minute historical circuit for unrelated instruments.
The old test explicitly required this behavior. A live BSE historical request
also returned `DH-905 Input_Exception`. The reproduction proves the defect,
but is not a count of how often it occurred during the failed production run.

## Dhan contract

- [Rate limits](https://dhanhq.co/docs/v2/#rate-limit): data APIs allow five
  requests per second and 100,000 per day. Quotes and orders have separate limits.
- [Error codes](https://dhanhq.co/docs/v2/annexure/): DH-905 means input error;
  DH-904 and 805 mean rate limiting. DH-908, DH-909 and 800 describe service or
  network errors.
- [Historical API](https://dhanhq.co/docs/v2/historical-data/): daily `toDate`
  is exclusive; intraday requests support a maximum 90-day range. Existing
  requests use 60 days of daily data and 30 days of five-minute data. Those
  ranges and exclusion of the current session remain unchanged.

The configured four-per-second admission remains unchanged. Redis admission
also enforces the daily budget; the current file fallback only tracks the
short window. Gateway HTTP 200 is not proof of a successful broker response.

## Changes

- Start at 06:00 IST. Allow up to three hours, capped at 09:00 for premarket
  runs. A 07:00 start gets two hours. Keep the existing 07:30 last-start rule,
  holiday checks and market-hours deferral. Post-close attempts get three hours.
- Historical instrument input/no-data errors no longer open a shared circuit.
  The existing single retry for transient input errors remains. Repeated
  service/network errors can still open the circuit; rate limits keep their
  adaptive cooldown.
- Honor the full advertised cooldown, bounded by the existing ten-minute retry
  budget, instead of repeatedly polling it every 30 seconds. Recognize raw
  DH-904/904 responses as retryable too.
- Log completed counts every minute even when workers are waiting. Add daily
  history and baseline durations to the completed run report.

Full publication, existing cache freshness, atomic latest replacement, the
four-day universe fallback, and venue selection rules remain intact. No
early publication with reduced coverage was introduced. A prolonged outage can
still prevent publication; the deadline bounds the work, not broker availability.

## Verification and rollout

The full existing backend suite with the installed Dhan SDK loaded passed:
286 tests, six skips, 25 subtests. An additional integration test passed through
daily history, baselines and actual JSON/Parquet publication. Broker calls in
these tests are fixtures; no live trading request is made.

The regression cases cover input errors, service circuits, rate-limit recovery,
the full cooldown wait, late starts, the 09:00 deadline, post-close runs, and
Intra-Finder reference refresh. Six tests in the Windows suite were skipped;
the Linux file-lock test is among them.

Deployment must reload both the market-data gateway and scanner because the
gateway owns the historical-service instance. Verify the next full scan's
duration and profile coverage on Ubuntu before claiming a measured runtime
improvement. Preserve the previous completed artifact during rollout. This
change was implemented and tested locally; production deployment and a full
live scan have not been performed in this task.
