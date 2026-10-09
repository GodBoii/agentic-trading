"""Causal momentum baseline. Parameters are hypotheses, not a fitted edge."""

from collections import deque

from .domain import PolicyConfig, Side, Signal, Tick


class MomentumPolicy:
    def __init__(self, config: PolicyConfig):
        self.config = config
        self.history: dict[int, deque[Tick]] = {}
        self.last_evaluated_minute: dict[int, int] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        cfg = self.config
        history = self.history.setdefault(tick.security_id, deque())
        if history and tick.at_us - history[-1].at_us > cfg.maximum_gap_seconds * 1_000_000:
            history.clear()
        if not tick.usable(cfg.maximum_trade_age_seconds, receipt_proxy=cfg.freshness_mode == "receipt_proxy"):
            history.clear()
            return None, "unusable_observation"
        history.append(tick)
        cutoff = tick.at_us - cfg.lookback_seconds * 1_000_000
        while len(history) > 1 and history[1].at_us <= cutoff:
            history.popleft()
        if history[0].at_us > cutoff:
            return None, "warming_history"
        minute = tick.at_us // 60_000_000
        if self.last_evaluated_minute.get(tick.security_id) == minute:
            return None, "between_evaluations"
        self.last_evaluated_minute[tick.security_id] = minute
        if tick.spread_bps > cfg.maximum_spread_bps:
            return None, "spread"
        recent_cutoff = tick.at_us - cfg.confirmation_seconds * 1_000_000
        recent = next((item for item in reversed(history) if item.at_us <= recent_cutoff), None)
        if recent is None:
            return None, "warming_confirmation"
        move = (tick.midpoint / history[0].midpoint - 1) * 10_000
        confirmation = (tick.midpoint / recent.midpoint - 1) * 10_000
        if not cfg.minimum_move_bps <= abs(move) <= cfg.maximum_move_bps:
            return None, "move"
        side = Side.LONG if move > 0 else Side.SHORT
        if side.sign * confirmation < cfg.confirmation_move_bps:
            return None, "confirmation"
        if cfg.require_vwap_alignment:
            if tick.vwap is None:
                return None, "vwap_unknown"
            if side.sign * (tick.midpoint - tick.vwap) <= 0:
                return None, "vwap_alignment"
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, move, confirmation), "signal"
