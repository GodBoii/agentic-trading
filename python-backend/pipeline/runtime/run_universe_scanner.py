from __future__ import annotations

import os
import time
from datetime import datetime

from pipeline.config import PipelineConfig
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.market_calendar_service import MarketCalendarService
from pipeline.services.storage_service import StorageService
from pipeline.stages.universe_scanner import UniverseScanner


def main() -> None:
    config = PipelineConfig()
    market_time = MarketTimeService(config)
    market_calendar = MarketCalendarService(config)
    last_run_date = ""
    retry_seconds = max(60, config.stage1_degraded_retry_interval_seconds)
    print("UNIVERSE SCANNER")
    while True:
        now = market_time.now()
        market_date = market_time.market_date_str()
        session = market_calendar.session_status()
        if not session.is_trading_day:
            print(f"Universe Scanner idle: {session.reason}")
            time.sleep(300)
            continue
        scheduled = datetime.strptime(config.stage1_schedule_time, "%H:%M").time()
        existing = StorageService.load_snapshot(config.stage1_daily_path(market_date))
        complete = bool(existing and (existing.get("summary") or {}).get("status") == "completed")
        baseline_current = bool(
            existing
            and int((existing.get("summary") or {}).get("baseline_schema_version") or 0)
            >= UniverseScanner.BASELINE_SCHEMA_VERSION
        )
        if complete and not baseline_current:
            try:
                print("Universe Scanner upgrading intraday baselines to the current schema.")
                existing = UniverseScanner(config).refresh_intraday_baselines(existing)
                baseline_current = True
                last_run_date = market_date
            except Exception as exc:
                print(f"Universe Scanner baseline upgrade failed: {type(exc).__name__}: {exc}")
                complete = False
        if now.time() >= scheduled and (last_run_date != market_date or not complete):
            try:
                max_isins = os.getenv("UNIVERSE_SCANNER_MAX_ISINS")
                result = UniverseScanner(config).run(int(max_isins) if max_isins else None)
                complete = (result.get("summary") or {}).get("status") == "completed"
                if complete:
                    last_run_date = market_date
            except Exception as exc:
                print(f"Universe Scanner failed: {type(exc).__name__}: {exc}")
            time.sleep(retry_seconds if not complete else 60)
        else:
            time.sleep(30)


if __name__ == "__main__":
    main()
