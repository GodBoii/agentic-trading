# September 11 resume verification

Resumed task `01a081a9-2cd8-7712-abb9-81805d8c3949` after its usage-limit
interruption. The research outputs and four production fixes were already on
disk. This continuation completed verification and corrected the stale Linux
verification status in the report. No production deployment or broker mutation
was performed.

## Checks completed

- Windows: `python-backend/trade/Scripts/python.exe -m pytest python-backend/tests -q`
  with `PYTHONPATH=python-backend`. Result: 278 passed, six skipped, 19 subtests
  passed in 23.07 seconds.
- Linux image: `docker compose -f docker-compose.validation.yml build tests`.
  Build succeeded using the local validation base image.
- Linux and isolated Redis: `docker compose -f docker-compose.validation.yml run --rm tests`.
  Result: 284 passed, 19 subtests passed in 46.74 seconds, no skips.
- `git diff --check` passed.
- Independent code review covered snapshot preparation, feature refresh,
  minute-volume accounting, rank timestamps and admission diagnostics. No
  actionable correctness issues were found.

## Existing sustained replay evidence

The prior continuation saved [sustained-feed.txt](sustained-feed.txt). It recorded
and verified all 420,000 packet sequences from 3,500 synthetic stocks. Elapsed
processing time was 121.62 seconds, p99 delay 554.03 ms, maximum delay 836.34 ms,
queue high-water mark 3,102, zero queue-full waits and no persistence error.
This continuation inspected that result without repeating the benchmark. It
does not demonstrate compliance with the 250 ms delay objective.

## Remaining work

The ranking experiment did not justify a replacement formula. The local fixes
refresh candidate metrics, conserve minute-boundary volume, expose admission
occupancy and fetch the initial quote after chart rendering. Pending-entry
expiry and cancellation reconciliation still need a defined lifecycle policy.
Feed stalls and morning profile publication remain separate engineering work.
