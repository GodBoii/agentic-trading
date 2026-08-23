from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.config import PipelineConfig
from pipeline.contracts import UNIVERSE_BASELINE_SCHEMA_VERSION
from pipeline.services.market_calendar_service import MarketCalendarService
from pipeline.services.market_time_service import MarketTimeService


def _load_summary(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    summary = payload.get("summary") if isinstance(payload, dict) else None
    return summary if isinstance(summary, dict) else None


def _artifact_complete(path: Path, market_date: str) -> bool:
    summary = _load_summary(path)
    return bool(
        summary
        and summary.get("status") == "completed"
        and summary.get("market_date") == market_date
        and int(summary.get("baseline_schema_version") or 0)
        >= UNIVERSE_BASELINE_SCHEMA_VERSION
    )


def _run_heavy_scan() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pipeline.runtime.run_universe_scanner_once"],
        check=False,
    )
    return int(completed.returncode)


def main() -> None:
    config = PipelineConfig()
    market_time = MarketTimeService(config)
    market_calendar = MarketCalendarService(config)
    last_run_date = ""
    retry_seconds = max(60, config.stage1_degraded_retry_interval_seconds)
    print("UNIVERSE SCANNER")
    print("Heavy scan work runs in an exit-after-run child process.", flush=True)
    while True:
        now = market_time.now()
        market_date = market_time.market_date_str()
        session = market_calendar.session_status()
        if not session.is_trading_day:
            print(f"Universe Scanner idle: {session.reason}", flush=True)
            time.sleep(300)
            continue

        scheduled = datetime.strptime(config.stage1_schedule_time, "%H:%M").time()
        if now.time() < scheduled or last_run_date == market_date:
            time.sleep(30)
            continue

        daily_path = config.stage1_daily_path(market_date)
        if _artifact_complete(daily_path, market_date):
            last_run_date = market_date
            print(
                f"Universe Scanner found a completed current artifact for {market_date}; idling.",
                flush=True,
            )
            time.sleep(30)
            continue

        return_code = _run_heavy_scan()
        complete = return_code == 0 and _artifact_complete(daily_path, market_date)
        if complete:
            last_run_date = market_date
        else:
            print(
                f"Universe Scanner child did not publish a complete artifact; "
                f"exit_code={return_code}. Retrying in {retry_seconds}s.",
                flush=True,
            )
        time.sleep(60 if complete else retry_seconds)


if __name__ == "__main__":
    main()
