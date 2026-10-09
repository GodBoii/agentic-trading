"""Execute three frozen opening-range hypotheses with the shared execution model."""

from importlib import import_module
from pathlib import Path

from research.common.runner import Variant, run_track

OpeningRangePolicy = import_module("research.02_opening_range.strategy").OpeningRangePolicy


def main() -> None:
    variants = [
        Variant("orb15", lambda cfg: OpeningRangePolicy(cfg, minutes=15),
                {"minutes": 15, "direction": False, "vwap": False},
                execution_overrides={"entry_start_second": 9*3600+30*60}),
        Variant("orb30_direction", lambda cfg: OpeningRangePolicy(cfg, minutes=30, require_direction=True),
                {"minutes": 30, "direction": True, "vwap": False},
                execution_overrides={"entry_start_second": 9*3600+45*60}),
        Variant("orb15_vwap", lambda cfg: OpeningRangePolicy(cfg, minutes=15, require_vwap=True),
                {"minutes": 15, "direction": False, "vwap": True},
                execution_overrides={"entry_start_second": 9*3600+30*60}),
    ]
    run_track(Path(__file__).resolve().parent, variants)


if __name__ == "__main__":
    main()
