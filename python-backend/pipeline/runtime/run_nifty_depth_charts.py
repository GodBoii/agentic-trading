from __future__ import annotations

import os

from pipeline.config import PipelineConfig
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.nifty_depth_charting import NiftyDepthChartGenerator


def main() -> None:
    config = PipelineConfig()
    market_date = os.getenv("NIFTY_CHART_MARKET_DATE") or MarketTimeService(config).market_date_str()
    bundle = NiftyDepthChartGenerator(config).generate_for_market_date(market_date)
    print(f"NIFTY depth charts generated for {market_date}: {bundle.get('generated')}")
    for chart_path in bundle.get("chart_paths_ordered") or []:
        print(chart_path)
    print(f"Manifest: {config.nifty_depth_charts_latest_path}")


if __name__ == "__main__":
    main()
