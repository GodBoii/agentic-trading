from pipeline.stages.stage1_sanitation import Stage1Sanitation


if __name__ == "__main__":
    print("`universe_scanner.py` now acts as a Stage 1 compatibility wrapper.")
    print("For the refactored pipeline use:")
    print("  - python -m pipeline.runtime.run_stage1")
    print("  - python -m pipeline.runtime.run_tick_collector")
    print("  - python -m pipeline.runtime.run_stage2_loop")
    Stage1Sanitation().run()
