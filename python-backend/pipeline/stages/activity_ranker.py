"""Cross-sectional activity ranking for the full live equity universe."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Dict, List, Optional

from pipeline.stages.live_state import InstrumentKey, LiveStockState


@dataclass(frozen=True)
class RankingResult:
    ranked: List[LiveStockState]
    hot: List[LiveStockState]
    eligible_count: int


class ActivityRanker:
    def __init__(
        self,
        *,
        hot_size: int = 60,
        reserve_size: int = 100,
        hysteresis_seconds: int = 60,
        max_packet_age_seconds: int = 10,
        max_trade_age_seconds: int = 90,
        max_spread_percent: float = 0.20,
    ) -> None:
        self.hot_size = max(1, hot_size)
        self.reserve_size = max(self.hot_size, reserve_size)
        self.hysteresis_seconds = max(0, hysteresis_seconds)
        self.max_packet_age_seconds = max(1, max_packet_age_seconds)
        self.max_trade_age_seconds = max(1, max_trade_age_seconds)
        self.max_spread_percent = max(0.0, max_spread_percent)
        self.last_hot_keys: set[InstrumentKey] = set()

    def rank(
        self,
        states: Dict[InstrumentKey, LiveStockState],
        now: datetime,
    ) -> RankingResult:
        eligible: List[LiveStockState] = []
        for state in states.values():
            state.refresh_derived(now)
            state.exclusion_reason = self._exclusion_reason(state, now)
            if state.exclusion_reason is None:
                eligible.append(state)

        volume_values = sorted(float(state.volume_pace or 0.0) for state in eligible)
        volatility_values = sorted(state.realized_volatility_percent for state in eligible)
        traded_values = sorted(state.traded_value_5m for state in eligible)
        returns = [state.return_percent(300, now.timestamp()) for state in eligible]
        market_return = float(median(returns)) if returns else 0.0
        relative_values = sorted(abs(value - market_return) for value in returns)
        for state, stock_return in zip(eligible, returns):
            state.volume_percentile = _percentile(volume_values, float(state.volume_pace or 0.0))
            state.volatility_percentile = _percentile(
                volatility_values, state.realized_volatility_percent
            )
            state.value_percentile = _percentile(traded_values, state.traded_value_5m)
            state.market_return_5m_percent = market_return
            state.relative_strength_5m_percent = stock_return - market_return
            state.relative_strength_percentile = _percentile(
                relative_values, abs(state.relative_strength_5m_percent)
            )
            # Both participation and movement are required. Value breaks ties and
            # cannot compensate for a motionless or inactive stock.
            state.hotness = min(state.volume_percentile, state.volatility_percentile)

        ranked = sorted(
            eligible,
            key=lambda state: (
                state.hotness,
                state.value_percentile,
                state.relative_strength_percentile,
                -(state.spread_percent or self.max_spread_percent),
            ),
            reverse=True,
        )
        now_ts = now.timestamp()
        reserve_keys = {state.key for state in ranked[: self.reserve_size]}
        hot_keys = {state.key for state in ranked[: self.hot_size]}
        for rank, state in enumerate(ranked, start=1):
            state.activity_rank = rank
            if state.key in hot_keys:
                state.is_hot = True
                state.hot_until = now_ts + self.hysteresis_seconds
            elif state.key in self.last_hot_keys and state.key in reserve_keys and now_ts <= state.hot_until:
                state.is_hot = True
                hot_keys.add(state.key)
            else:
                state.is_hot = False

        eligible_keys = {state.key for state in eligible}
        for state in states.values():
            if state.key not in eligible_keys:
                state.is_hot = False
                state.activity_rank = None
                state.hotness = 0.0
        self.last_hot_keys = hot_keys
        hot = [state for state in ranked if state.key in hot_keys]
        return RankingResult(ranked=ranked, hot=hot, eligible_count=len(eligible))

    def _exclusion_reason(self, state: LiveStockState, now: datetime) -> Optional[str]:
        if state.latest_price <= 0 or not state.last_packet_at:
            return "PRICE_UNAVAILABLE"
        try:
            packet_age = (now - datetime.fromisoformat(state.last_packet_at)).total_seconds()
        except ValueError:
            return "PACKET_TIME_INVALID"
        if packet_age > self.max_packet_age_seconds:
            return "PACKET_STALE"
        trade_age = state.trade_age_seconds(now)
        if trade_age is not None and trade_age > self.max_trade_age_seconds:
            return "LAST_TRADE_STALE"
        if len(state.depth) < 5:
            return "DEPTH_INCOMPLETE"
        if state.spread_percent is None or state.spread_percent > self.max_spread_percent:
            return "SPREAD_TOO_WIDE"
        if _near_circuit(state):
            return "CIRCUIT_PROXIMITY"
        return None


def _percentile(ordered: List[float], value: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return 100.0
    lower = bisect_left(ordered, value)
    upper = bisect_right(ordered, value)
    return ((lower + upper) / 2.0) / len(ordered) * 100.0


def _near_circuit(state: LiveStockState) -> bool:
    if state.upper_circuit and state.latest_price >= state.upper_circuit * 0.998:
        return True
    if state.lower_circuit and state.latest_price <= state.lower_circuit * 1.002:
        return True
    return False
