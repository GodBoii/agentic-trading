from pipeline.config import PipelineConfig
from pipeline.runtime.run_sorting import ensure_current_stage1_snapshot
from pipeline.stages.stage2_momentum_ignition import Stage2MomentumIgnition


if __name__ == "__main__":
    config = PipelineConfig()
    ensure_current_stage1_snapshot(config)
    Stage2MomentumIgnition(config).run()
