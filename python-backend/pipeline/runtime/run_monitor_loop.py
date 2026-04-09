import threading
import time

from pipeline.config import PipelineConfig
from pipeline.runtime.run_backend import wait_for_current_stage1_snapshot
from pipeline.runtime.run_tick_collector import TickCollector
from pipeline.stages.stage2_liquidity_gate import Stage2LiquidityGate


def run_monitor_loop(config: PipelineConfig) -> None:
    monitor = Stage2LiquidityGate(config)

    while True:
        print("\nStarting Monitor cycle...")
        wait_for_current_stage1_snapshot(config)
        monitor.run()
        print(
            f"Sleeping for {config.monitor_loop_interval_seconds} seconds before next Monitor cycle..."
        )
        time.sleep(config.monitor_loop_interval_seconds)


def main() -> None:
    config = PipelineConfig()

    print("=" * 60)
    print("MONITOR ORCHESTRATOR")
    print("=" * 60)

    wait_for_current_stage1_snapshot(config)
    print("Stage 1 is ready. Starting live monitor.")

    tick_thread = threading.Thread(
        target=TickCollector(config).run,
        name="tick-collector",
        daemon=True,
    )
    tick_thread.start()
    print("Tick collector started. Entering monitor loop.")
    print(f"Monitor loop interval: {config.monitor_loop_interval_seconds} seconds")

    run_monitor_loop(config)


if __name__ == "__main__":
    main()
