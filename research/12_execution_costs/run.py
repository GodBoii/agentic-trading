"""Freeze one signal policy; vary execution assumptions rather than optimize alpha."""

from pathlib import Path

from research.common.runner import Variant, run_track
from research.intraday_lab.policy import MomentumPolicy
from .strategy import NoTradePolicy


def variants() -> list[Variant]:
    hypothesis = {"signal": "unchanged MomentumPolicy", "role": "execution sensitivity"}
    return [
        Variant("base_execution", MomentumPolicy, hypothesis),
        Variant("footprint_1pct", MomentumPolicy,
                {**hypothesis, "footprint": "1% aggregate top-five depth, still not top-quote capacity"},
                execution_overrides={"aggregate_depth_fraction": .01}),
        Variant("delay_3s_slippage_3bps", MomentumPolicy,
                {**hypothesis, "stress": "joint latency and slippage scenario; cannot separate individual effects"},
                execution_overrides={"latency_ms": 3000, "extra_slippage_bps": 3}),
        Variant("no_trade_control", lambda config: NoTradePolicy(),
                {"signal": "never trade", "role": "accounting and activity control"}),
    ]


def main() -> None:
    run_track(Path(__file__).parent, variants())


if __name__ == "__main__":
    main()
