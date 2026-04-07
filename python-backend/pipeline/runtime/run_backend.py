import threading
import time

from pipeline.config import PipelineConfig
from pipeline.runtime.run_tick_collector import TickCollector
from pipeline.services.market_time_service import MarketTimeService
from pipeline.stages.stage1_sanitation import Stage1Sanitation
from pipeline.stages.stage2_liquidity_gate import Stage2LiquidityGate


def run_stage2_loop(config: PipelineConfig) -> None:
    stage2 = Stage2LiquidityGate(config)

    while True:
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

    stage1_daily_path = config.stage1_daily_path(market_date)
    if stage1_daily_path.exists():
        print(
            f"Stage 1 daily output found: {stage1_daily_path.name}. "
            "Skipping Stage 1 and continuing to Stage 2."
        )
    else:
        print(
            f"Stage 1 daily output not found: {stage1_daily_path.name}. "
            "Running Stage 1 now."
        )
        Stage1Sanitation(config).run()
        print("Stage 1 finished for today. Continuing to Stage 2.")

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
