from pipeline.config import PipelineConfig
from pipeline.runtime.run_backend import ensure_current_stage1_snapshot
from pipeline.stages.stage2_liquidity_gate import Stage2LiquidityGate


if __name__ == "__main__":
    config = PipelineConfig()
    ensure_current_stage1_snapshot(config)
    Stage2LiquidityGate(config).run()
