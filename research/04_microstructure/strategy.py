"""Causal top-five snapshot proxies, not reconstructed event OFI or microprice."""

from collections import deque
from dataclasses import dataclass
from math import isfinite

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick


def aggregate_imbalance(tick: Tick) -> float:
    total = tick.bid_quantity_5 + tick.ask_quantity_5
    if total <= 0:
        raise ValueError("positive aggregate displayed depth required")
    return (tick.bid_quantity_5 - tick.ask_quantity_5) / total


def aggregate_weighted_quote(tick: Tick) -> float:
    """Quote weighted by top-five totals. This is deliberately not called microprice."""
    total = tick.bid_quantity_5 + tick.ask_quantity_5
    if total <= 0 or tick.bid <= 0 or tick.ask < tick.bid:
        raise ValueError("positive depth and valid ordered quote required")
    return (tick.ask * tick.bid_quantity_5 + tick.bid * tick.ask_quantity_5) / total


def normalized_depth_change(previous: Tick, current: Tick) -> float:
    """Changes in snapshot totals cannot identify adds, cancels, or executions."""
    total = previous.bid_quantity_5 + previous.ask_quantity_5
    if total <= 0:
        raise ValueError("positive previous aggregate depth required")
    return ((current.bid_quantity_5 - previous.bid_quantity_5)
            - (current.ask_quantity_5 - previous.ask_quantity_5)) / total


@dataclass(frozen=True)
class MicrostructureConfig:
    method: str = "imbalance_persistence"
    imbalance_threshold: float = 0.4
    persistence_seconds: int = 30
    change_threshold: float = 0.25
    weighted_offset_bps: float = 0.4
    confirmation_move_bps: float = 1.0

    def __post_init__(self) -> None:
        if self.method not in {"imbalance_persistence", "depth_change", "weighted_quote_trend"}:
            raise ValueError("unknown snapshot hypothesis")
        if not 0 < self.imbalance_threshold < 1 or self.persistence_seconds < 1:
            raise ValueError("invalid imbalance or persistence")
        if any(not isfinite(x) or x <= 0 for x in
               (self.change_threshold, self.weighted_offset_bps, self.confirmation_move_bps)):
            raise ValueError("finite positive thresholds required")


class MicrostructurePolicy:
    def __init__(self, policy: PolicyConfig, config: MicrostructureConfig):
        self.policy = policy
        self.config = config
        self.history: dict[int, deque[Tick]] = {}
        self.last_evaluation: dict[int, int] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        history = self.history.setdefault(tick.security_id, deque())
        if not tick.usable(self.policy.maximum_trade_age_seconds,
                           receipt_proxy=self.policy.freshness_mode == "receipt_proxy"):
            history.clear()
            return None, "unusable_observation"
        if history and (tick.at_us <= history[-1].at_us or
                        tick.at_us - history[-1].at_us > self.policy.maximum_gap_seconds * 1e6):
            history.clear()
        history.append(tick)
        cutoff = tick.at_us - self.config.persistence_seconds * 1_000_000
        while len(history) > 1 and history[1].at_us <= cutoff:
            history.popleft()
        if history[0].at_us > cutoff:
            return None, "warming_history"
        minute = tick.at_us // 60_000_000
        if self.last_evaluation.get(tick.security_id) == minute:
            return None, "between_evaluations"
        self.last_evaluation[tick.security_id] = minute
        if tick.spread_bps > self.policy.maximum_spread_bps:
            return None, "spread"
        cfg = self.config
        imbalance = aggregate_imbalance(tick)
        side = Side.LONG if imbalance > 0 else Side.SHORT
        move = (tick.midpoint / history[0].midpoint - 1) * 10_000
        if cfg.method == "imbalance_persistence":
            values = [aggregate_imbalance(item) for item in history]
            if any(side.sign * value < cfg.imbalance_threshold for value in values):
                return None, "imbalance_not_persistent"
            strength = imbalance
        elif cfg.method == "depth_change":
            strength = normalized_depth_change(history[0], tick)
            side = Side.LONG if strength > 0 else Side.SHORT
            if abs(strength) < cfg.change_threshold or side.sign * imbalance < cfg.imbalance_threshold:
                return None, "depth_change"
        else:
            strength = (aggregate_weighted_quote(tick) / tick.midpoint - 1) * 10_000
            if abs(strength) < cfg.weighted_offset_bps or side.sign * move < cfg.confirmation_move_bps:
                return None, "weighted_quote_trend"
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, move, strength), "signal"
