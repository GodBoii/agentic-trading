from pathlib import Path

from research.common.runner import Variant, run_track
from .strategy import VarianceRatioPolicy


def main() -> None:
    variants = [Variant(
        name=name, factory=lambda cfg, lag=lag, adaptive=adaptive: VarianceRatioPolicy(cfg, lag=lag, adaptive=adaptive),
        parameters={"lag": lag, "adaptive": adaptive, "return_window_minutes": 30,
                    "trend_ratio": 1.25, "reversion_ratio": .75, "minimum_move_bps": 10})
        for name, lag, adaptive in (("trend_q2", 2, False), ("adaptive_q2", 2, True), ("adaptive_q5", 5, True))]
    run_track(Path(__file__).parent, variants)


if __name__ == "__main__":
    main()
