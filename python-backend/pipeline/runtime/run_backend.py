from pipeline.runtime.run_sorting import (
    ensure_current_stage1_snapshot,
    main,
    run_stage2_loop,
    wait_for_current_stage1_snapshot,
    wait_for_current_stage2_snapshot,
)


if __name__ == "__main__":
    main()
