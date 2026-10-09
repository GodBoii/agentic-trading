"""Run two frozen VWAP setup-state-machine hypotheses."""

from pathlib import Path

from research.common.runner import Variant, run_track
from .strategy import VARIANTS, VWAPPullbackPolicy


def main() -> None:
    variants = [Variant(name=name, factory=VWAPPullbackPolicy,
                        parameters={"bar_seconds": 60, "trend_bars": 5,
                                    "minimum_vwap_slope_bps": 1.0,
                                    "minimum_trend_move_bps": 8.0,
                                    "armed_deviation_range_bps": [10, 80],
                                    "setup_expiry_bars": 5,
                                    "invalidation_deviation_range_bps": [-10, 100],
                                    "touch_range_bps": [-5, 5] if name == "vwap_reclaim" else [2, 10],
                                    "confirmation_deviation_bps": 8 if name == "vwap_reclaim" else 15,
                                    "minimum_confirmation_move_bps": 3.0},
                        policy_overrides={"target_bps": 30.0, "stop_bps": 20.0,
                                          "horizon_seconds": 600, "cooldown_seconds": 600,
                                          "require_cost_room": True}) for name in VARIANTS]
    run_track(Path(__file__).parent, variants)


if __name__ == "__main__":
    main()
