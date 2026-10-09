"""Run three preregistered indicator/pattern rules."""

from pathlib import Path

from research.common.runner import Variant, run_track
from .strategy import IndicatorPolicy, VARIANTS


def main() -> None:
    parameters = {
        "rsi_recross": {"bar_seconds": 60, "history_bars": 21,
                        "rsi_period": 14, "low": 30.0, "high": 70.0},
        "bollinger_breakout": {"bar_seconds": 60, "history_bars": 20,
                               "sigma_multiple": 2.0, "minimum_confirmation_bps": 3.0,
                               "minimum_sigma_bps": 2.0},
        "wick_rejection": {"bar_seconds": 60, "minimum_range_bps": 10.0,
                           "minimum_wick_fraction": .60, "maximum_body_fraction": .25,
                           "close_edge_fraction": .25, "prior_extreme_bars": 5},
    }
    variants = [Variant(name=name, factory=IndicatorPolicy, parameters=parameters[name],
                        policy_overrides={"target_bps": 30.0, "stop_bps": 20.0,
                                          "horizon_seconds": 600, "cooldown_seconds": 600,
                                          "require_cost_room": True}) for name in VARIANTS]
    run_track(Path(__file__).parent, variants)


if __name__ == "__main__":
    main()
