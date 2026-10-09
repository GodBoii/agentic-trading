"""Run three preregistered snapshot hypotheses on the fixed historical cohort."""

from dataclasses import asdict
from pathlib import Path

from research.common.runner import Variant, run_track
from .strategy import MicrostructureConfig, MicrostructurePolicy


def main() -> None:
    variants = []
    for method in ("imbalance_persistence", "depth_change", "weighted_quote_trend"):
        config = MicrostructureConfig(method=method)
        variants.append(Variant(method, lambda policy, config=config: MicrostructurePolicy(policy, config),
                                asdict(config), {"horizon_seconds": 60, "cooldown_seconds": 180}))
    run_track(Path(__file__).parent, variants)


if __name__ == "__main__":
    main()
