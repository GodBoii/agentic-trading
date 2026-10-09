"""Run frozen hypotheses with the common account and provenance writer."""

from pathlib import Path

from research.common.runner import Variant, run_track
from .strategy import ReversionPolicy, VARIANTS


def main() -> None:
    variants = [Variant(name=name, factory=ReversionPolicy,
                        parameters={"bar_seconds": 60, "history_bars": 20,
                                    "zscore_threshold": 2.0, "minimum_deviation_bps": 15.0,
                                    "vwap_minimum_deviation_bps": 25.0,
                                    "maximum_deviation_bps": 120.0,
                                    "minimum_turn_bps": 1.0,
                                    "ou_half_life_min_bars": 2.0,
                                    "ou_half_life_max_bars": 15.0},
                        policy_overrides={"target_bps": 30.0, "stop_bps": 20.0,
                                          "horizon_seconds": 600, "cooldown_seconds": 600,
                                          "require_cost_room": True}) for name in VARIANTS]
    run_track(Path(__file__).parent, variants)


if __name__ == "__main__":
    main()
