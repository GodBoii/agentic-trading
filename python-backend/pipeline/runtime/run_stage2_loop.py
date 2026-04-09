import time

from pipeline.config import PipelineConfig
from pipeline.runtime.run_sorting import ensure_current_stage1_snapshot
from pipeline.stages.stage2_momentum_ignition import Stage2MomentumIgnition


if __name__ == "__main__":
    config = PipelineConfig()
    stage2 = Stage2MomentumIgnition(config)

    while True:
        print("\nStarting Stage 2 cycle...")
        ensure_current_stage1_snapshot(config)
        stage2.run()
        print(f"Sleeping for {config.stage2_loop_interval_seconds} seconds before next Stage 2 cycle...")
        time.sleep(config.stage2_loop_interval_seconds)
