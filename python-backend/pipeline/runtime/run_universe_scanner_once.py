from __future__ import annotations

import os

from pipeline.config import PipelineConfig
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService
from pipeline.stages.universe_scanner import UniverseScanner


def main() -> int:
    config = PipelineConfig()
    market_time = MarketTimeService(config)
    market_date = market_time.market_date_str()
    existing = StorageService.load_snapshot(config.stage1_daily_path(market_date))
    summary = (existing or {}).get("summary") or {}
    complete = summary.get("status") == "completed"
    baseline_current = (
        int(summary.get("baseline_schema_version") or 0)
        >= UniverseScanner.BASELINE_SCHEMA_VERSION
    )

    try:
        if complete and not baseline_current:
            print(
                "Universe Scanner upgrading intraday baselines to the current schema.",
                flush=True,
            )
            result = UniverseScanner(config).refresh_intraday_baselines(existing)
        elif complete:
            return 0
        else:
            max_isins = os.getenv("UNIVERSE_SCANNER_MAX_ISINS")
            result = UniverseScanner(config).run(int(max_isins) if max_isins else None)
    except Exception as exc:
        print(f"Universe Scanner failed: {type(exc).__name__}: {exc}", flush=True)
        return 1

    final_summary = (result or {}).get("summary") or {}
    return 0 if final_summary.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
