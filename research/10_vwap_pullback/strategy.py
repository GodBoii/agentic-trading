"""Explicit trend, pullback, confirmation states on completed midpoint bars."""

from dataclasses import dataclass, replace
from enum import Enum

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick

from .bars import CompletedBars


VARIANTS = ("vwap_reclaim", "vwap_bounded_pullback")


class Stage(str, Enum):
    ARMED = "ARMED"
    TOUCHED = "TOUCHED"


@dataclass(frozen=True, slots=True)
class Setup:
    side: Side
    stage: Stage
    armed_minute: int
    touched_minute: int | None = None


def configuration(variant: str, freshness_mode: str = "recent_trade") -> PolicyConfig:
    if variant not in VARIANTS:
        raise ValueError("unknown pullback variant")
    return replace(PolicyConfig(), name=variant, freshness_mode=freshness_mode,
                   target_bps=30.0, stop_bps=20.0, horizon_seconds=600,
                   cooldown_seconds=600, require_cost_room=True)


class VWAPPullbackPolicy:
    def __init__(self, config: PolicyConfig):
        if config.name not in VARIANTS:
            raise ValueError("unknown pullback variant")
        self.config = config
        self.bars = CompletedBars(config)
        self.setups: dict[int, Setup] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        bar, reason = self.bars.update(tick)
        sid = tick.security_id
        if bar is None:
            if reason in {"unusable_observation", "warming_bar", "incomplete_bar"}:
                self.setups.pop(sid, None)
            return None, reason
        if tick.spread_bps > self.config.maximum_spread_bps:
            self.setups.pop(sid, None)
            return None, "spread"
        bars = list(self.bars.history[sid])
        if len(bars) < 6:
            return None, "warming_history"
        recent = bars[-6:]
        if any(b.vwap is None for b in recent):
            self.setups.pop(sid, None)
            return None, "vwap_unknown"
        deviation = (bar.close / bar.vwap - 1) * 10_000
        slope = (bar.vwap / recent[0].vwap - 1) * 10_000
        trend_move = (bar.close / recent[0].close - 1) * 10_000
        turn = (bar.close / bars[-2].close - 1) * 10_000
        setup = self.setups.get(sid)
        if setup is None:
            side = Side.LONG if slope > 0 else Side.SHORT
            if side.sign * slope < 1 or side.sign * trend_move < 8 or not 10 <= side.sign * deviation <= 80:
                return None, "trend_absent"
            self.setups[sid] = Setup(side, Stage.ARMED, bar.minute)
            return None, "setup_armed"
        signed = setup.side.sign * deviation
        if bar.minute - setup.armed_minute > 5:
            self.setups.pop(sid, None)
            return None, "setup_expired"
        if setup.side.sign * slope < 0 or signed < -10 or signed > 100:
            self.setups.pop(sid, None)
            return None, "setup_invalidated"
        if setup.stage is Stage.ARMED:
            low, high = (-5.0, 5.0) if self.config.name == "vwap_reclaim" else (2.0, 10.0)
            if low <= signed <= high:
                self.setups[sid] = replace(setup, stage=Stage.TOUCHED, touched_minute=bar.minute)
                return None, "pullback_touched"
            return None, "waiting_pullback"
        threshold = 8 if self.config.name == "vwap_reclaim" else 15
        if bar.minute <= setup.touched_minute or signed < threshold or setup.side.sign * turn < 3:
            return None, "waiting_confirmation"
        self.setups.pop(sid, None)
        return Signal(tick.at_us, sid, setup.side, tick.midpoint, deviation, turn), "signal"
