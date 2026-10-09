"""Execute three frozen volatility-compression hypotheses."""

from importlib import import_module
from pathlib import Path

from research.common.runner import Variant, run_track

CompressionPolicy = import_module("research.06_volatility_compression.strategy").CompressionPolicy


def main() -> None:
    variants = [
        Variant("bollinger_relative", lambda cfg: CompressionPolicy(cfg),
                {"bars": 20, "width_history": 125, "armed_bars": 10, "confirmation_bars": 2}),
        Variant("bollinger_absolute15", lambda cfg: CompressionPolicy(cfg, method="bollinger_absolute"),
                {"bars": 20, "maximum_width_bps": 15, "armed_bars": 10, "confirmation_bars": 2}),
        Variant("compressed_range5", lambda cfg: CompressionPolicy(cfg, method="range", confirmation_bars=1),
                {"bars": 5, "maximum_width_bps": 15, "confirmation_bars": 1}),
    ]
    run_track(Path(__file__).resolve().parent, variants)


if __name__ == "__main__":
    main()
