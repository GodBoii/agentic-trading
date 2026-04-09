import time

from pipeline.config import PipelineConfig
from pipeline.services.market_time_service import MarketTimeService
from pipeline.stages.stage1_sanitation import Stage1Sanitation
from pipeline.stages.stage2_momentum_ignition import Stage2MomentumIgnition


def ensure_current_stage1_snapshot(config: PipelineConfig) -> str:
    clock = MarketTimeService(config)
    market_date = clock.market_date_str()
    stage1_daily_path = config.stage1_daily_path(market_date)
    if stage1_daily_path.exists():
        print(
            f"Stage 1 daily output found: {stage1_daily_path.name}. "
            "Skipping Stage 1 and continuing."
        )
        return market_date

    print(
        f"Stage 1 daily output not found: {stage1_daily_path.name}. "
        "Running Stage 1 now."
    )
    Stage1Sanitation(config).run()
    print("Stage 1 finished for current market date.")
    return market_date


def wait_for_current_stage1_snapshot(
    config: PipelineConfig,
    poll_seconds: int = 15,
) -> str:
    clock = MarketTimeService(config)
    market_date = clock.market_date_str()
    stage1_daily_path = config.stage1_daily_path(market_date)

    while not stage1_daily_path.exists():
        print(
            f"Stage 1 daily output not found yet: {stage1_daily_path.name}. "
            f"Waiting {poll_seconds}s for sorting to produce it."
        )
        time.sleep(poll_seconds)

    print(
        f"Stage 1 daily output found: {stage1_daily_path.name}. "
        "Using it for the current market date."
    )
    return market_date


def wait_for_current_stage2_snapshot(
    config: PipelineConfig,
    poll_seconds: int = 15,
) -> str:
    clock = MarketTimeService(config)
    market_date = clock.market_date_str()
    stage2_daily_path = config.stage2_daily_path(market_date)

    while not stage2_daily_path.exists():
        print(
            f"Stage 2 daily output not found yet: {stage2_daily_path.name}. "
            f"Waiting {poll_seconds}s for sorting to produce it."
        )
        time.sleep(poll_seconds)

    print(
        f"Stage 2 daily output found: {stage2_daily_path.name}. "
        "Using it for the current market date."
    )
    return market_date


def run_stage2_loop(config: PipelineConfig) -> None:
    stage2 = Stage2MomentumIgnition(config)

    while True:
        print("\nStarting Stage 2 cycle...")
        ensure_current_stage1_snapshot(config)
        stage2.run()
        print(
            f"Sleeping for {config.stage2_loop_interval_seconds} seconds before next Stage 2 cycle..."
        )
        time.sleep(config.stage2_loop_interval_seconds)


def main() -> None:
    config = PipelineConfig()
    clock = MarketTimeService(config)

    print("=" * 60)
    print("SORTING ORCHESTRATOR")
    print("=" * 60)
    print(f"Current market time: {clock.market_status_text()}")

    ensure_current_stage1_snapshot(config)
    print("Stage 1 is ready. Continuing to Stage 2.")
    print("Entering Stage 2 momentum loop.")
    print(f"Stage 2 loop interval: {config.stage2_loop_interval_seconds} seconds")

    run_stage2_loop(config)


if __name__ == "__main__":
    main()
