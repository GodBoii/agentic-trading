"""Frozen exit-distance and holding-time comparisons using unchanged raw entries."""

from importlib import import_module
from pathlib import Path

from research.common.runner import Variant, run_track
from research.intraday_lab.policy import MomentumPolicy

ExitSpec = import_module("research.11_exit_math.strategy").ExitSpec


def main() -> None:
    specs = [
        ("fixed_30_15_300", ExitSpec(30, 15, 300)),
        ("double_distances_60_30_300", ExitSpec(60, 30, 300)),
        ("short_time_30_15_60", ExitSpec(30, 15, 60)),
    ]
    variants = [Variant(name, MomentumPolicy,
                        {"entry": "unchanged_causal_momentum", **spec.policy_overrides(),
                         "adaptive_volatility": False}, policy_overrides=spec.policy_overrides())
                for name, spec in specs]
    run_track(Path(__file__).resolve().parent, variants)


if __name__ == "__main__":
    main()
