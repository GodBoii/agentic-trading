import threading
import time
import os

from pipeline.config import PipelineConfig
from pipeline.runtime.run_sorting import wait_for_current_stage2_snapshot
from pipeline.runtime.run_tick_collector import TickCollector
from pipeline.services.nifty_depth_monitor import NiftyDepthMonitor
from pipeline.stages.stage2_liquidity_gate import Stage2LiquidityGate


def run_monitor_loop(config: PipelineConfig) -> None:
    monitor = Stage2LiquidityGate(config)

    while True:
        print("\nStarting Monitor cycle...")
        wait_for_current_stage2_snapshot(config)
        monitor.run()
        print(
            f"Sleeping for {config.monitor_loop_interval_seconds} seconds before next Monitor cycle..."
        )
        time.sleep(config.monitor_loop_interval_seconds)


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def run_legacy_stage2_liquidity_monitor(config: PipelineConfig) -> None:
    wait_for_current_stage2_snapshot(config)
    print("Stage 2 shortlist is ready. Starting live monitor.")

    tick_thread = threading.Thread(
        target=TickCollector(config).run,
        name="tick-collector",
        daemon=True,
    )
    tick_thread.start()
    print("Tick collector started. Entering monitor loop.")
    print(f"Monitor loop interval: {config.monitor_loop_interval_seconds} seconds")

    run_monitor_loop(config)


def main() -> None:
    config = PipelineConfig()

    print("=" * 60)
    print("MONITOR ORCHESTRATOR")
    print("=" * 60)

    if not _env_bool("MONITOR_LEGACY_LIQUIDITY_ENABLED", False):
        print("Running NIFTY market-structure monitor as the primary monitor.")
        print("Set MONITOR_LEGACY_LIQUIDITY_ENABLED=1 to also run the old Stage 2 liquidity gate.")
        NiftyDepthMonitor(config).run()
        return

    nifty_depth_thread = threading.Thread(
        target=NiftyDepthMonitor(config).run,
        name="nifty-market-structure-monitor",
        daemon=True,
    )
    nifty_depth_thread.start()
    print("NIFTY market-structure monitor started.")
    print("Legacy Stage 2 liquidity gate enabled.")
    run_legacy_stage2_liquidity_monitor(config)


if __name__ == "__main__":
    main()
