"""Causal equal-weight peer residuals, without pretending to hedge a portfolio."""

from collections import deque
from statistics import mean

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick


class PeerResidualPolicy:
    def __init__(self, config: PolicyConfig, *, direction: str = "continuation",
                 threshold_bps: float = 10.0, minimum_peers: int = 4):
        if direction not in {"continuation", "reversal", "confirmed_reversal"}:
            raise ValueError("unknown residual direction")
        if minimum_peers < 1 or threshold_bps <= 0:
            raise ValueError("positive peer count and threshold required")
        self.config = config
        self.direction = direction
        self.threshold = threshold_bps
        self.minimum_peers = minimum_peers
        self.histories: dict[int, deque[Tick]] = {}
        self.returns: dict[int, tuple[int, float]] = {}
        self.evaluated: dict[int, int] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        cfg = self.config
        history = self.histories.setdefault(tick.security_id, deque())
        if history and tick.at_us - history[-1].at_us > cfg.maximum_gap_seconds * 1_000_000:
            history.clear()
            self.returns.pop(tick.security_id, None)
        if not tick.usable(cfg.maximum_trade_age_seconds, receipt_proxy=cfg.freshness_mode == "receipt_proxy"):
            history.clear()
            self.returns.pop(tick.security_id, None)
            return None, "unusable"
        history.append(tick)
        cutoff = tick.at_us - cfg.lookback_seconds * 1_000_000
        while len(history) > 1 and history[1].at_us <= cutoff:
            history.popleft()
        if history[0].at_us > cutoff:
            return None, "history"
        own = (tick.midpoint / history[0].midpoint - 1) * 10_000
        self.returns[tick.security_id] = (tick.at_us, own)
        minute = tick.at_us // 60_000_000
        if self.evaluated.get(tick.security_id) == minute:
            return None, "between_evaluations"
        self.evaluated[tick.security_id] = minute
        peers = [value for sid, (at, value) in self.returns.items()
                 if sid != tick.security_id and 0 <= tick.at_us - at <= cfg.maximum_gap_seconds * 1_000_000]
        if len(peers) < self.minimum_peers:
            return None, "insufficient_fresh_peers"
        if tick.spread_bps > cfg.maximum_spread_bps:
            return None, "spread"
        residual = own - mean(peers)
        if not self.threshold <= abs(residual) <= cfg.maximum_move_bps:
            return None, "residual"
        recent = next((t for t in reversed(history)
                       if t.at_us <= tick.at_us - cfg.confirmation_seconds * 1_000_000), None)
        if recent is None:
            return None, "confirmation_history"
        confirmation = (tick.midpoint / recent.midpoint - 1) * 10_000
        direction = 1 if residual > 0 else -1
        if self.direction != "continuation":
            direction *= -1
        if self.direction == "confirmed_reversal" and direction * confirmation < 2.0:
            return None, "reversal_not_confirmed"
        return Signal(tick.at_us, tick.security_id, Side.LONG if direction > 0 else Side.SHORT,
                      tick.midpoint, residual, confirmation), "signal"
