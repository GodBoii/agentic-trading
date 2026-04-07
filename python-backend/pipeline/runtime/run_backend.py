import threading
import time

from pipeline.config import PipelineConfig
from pipeline.runtime.run_tick_collector import TickCollector
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService
from pipeline.stages.stage1_sanitation import Stage1Sanitation
from pipeline.stages.stage2_liquidity_gate import Stage2LiquidityGate


def run_stage2_loop(config: PipelineConfig) -> None:
    stage2 = Stage2LiquidityGate(config)
    clock = MarketTimeService(config)

    while True:
        if not clock.is_market_hours():
            print(
                "Stage 2 waiting for market hours. "
                f"Current time: {clock.market_status_text()} | "
                f"Market window: {config.market_open_hour:02d}:{config.market_open_minute:02d}"
                f"-{config.market_close_hour:02d}:{config.market_close_minute:02d}"
            )
            time.sleep(60)
            continue

        print("\nStarting Stage 2 cycle...")
        stage2.run()
        print(
            f"Sleeping for {config.stage2_loop_interval_seconds} seconds before next Stage 2 cycle..."
        )
        time.sleep(config.stage2_loop_interval_seconds)


def main() -> None:
    config = PipelineConfig()
    clock = MarketTimeService(config)
    market_date = clock.market_date_str()

    print("=" * 60)
    print("TRADING BACKEND ORCHESTRATOR")
    print("=" * 60)
    print(f"Current market time: {clock.market_status_text()}")

    if StorageService.is_snapshot_for_market_date(
        config.stage1_latest_path,
        config.market_timezone,
        market_date,
    ):
        print(
            f"Stage 1 already completed for market date {market_date}. "
            "Skipping Stage 1 and continuing to Stage 2."
        )
    else:
        print(
            f"Stage 1 snapshot for market date {market_date} not found. "
            "Running Stage 1 now."
        )
        Stage1Sanitation(config).run()
        print("Stage 1 finished for today. Continuing to Stage 2.")

    while not clock.is_market_hours():
        print(
            "Stage 2 is waiting for market hours. "
            f"Current time: {clock.market_status_text()} | "
            f"Market window: {config.market_open_hour:02d}:{config.market_open_minute:02d}"
            f"-{config.market_close_hour:02d}:{config.market_close_minute:02d}"
        )
        time.sleep(60)

    tick_thread = threading.Thread(
        target=TickCollector(config).run,
        name="tick-collector",
        daemon=True,
    )
    tick_thread.start()
    print("Tick collector started. Entering Stage 2 live loop.")

    run_stage2_loop(config)


if __name__ == "__main__":
    main()
