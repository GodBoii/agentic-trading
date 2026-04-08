import time

from pipeline.config import PipelineConfig
from pipeline.runtime.run_backend import ensure_current_stage1_snapshot
from pipeline.stages.stage2_liquidity_gate import Stage2LiquidityGate


if __name__ == "__main__":
    config = PipelineConfig()
    stage2 = Stage2LiquidityGate(config)

    while True:
        print("\nStarting Stage 2 cycle...")
        ensure_current_stage1_snapshot(config)
        stage2.run()
        print(f"Sleeping for {config.stage2_loop_interval_seconds} seconds before next Stage 2 cycle...")
        time.sleep(config.stage2_loop_interval_seconds)
