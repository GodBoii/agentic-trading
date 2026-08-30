import time
from typing import Dict, List, Optional
import numpy as np

from pipeline.stages.live_state import LiveStockState
from pipeline.services.market_time_service import MarketTimeService


class ActivityRanker:
    def __init__(self, market_time: MarketTimeService, top_n: int = 50, hysteresis_seconds: int = 300):
        self.market_time = market_time
        self.top_n = top_n
        self.hysteresis_seconds = hysteresis_seconds

    def rank(self, states: Dict[int, LiveStockState]) -> List[LiveStockState]:
        """
        Rank all stocks and return the top active ones.
        Updates the hotness fields on the state objects.
        """
        now = time.time()
        market_now = self.market_time.now()
        market_hhmm = market_now.strftime("%H:%M")
        
        session_elapsed_seconds = max(1.0, (market_now - market_now.replace(hour=9, minute=15, second=0, microsecond=0)).total_seconds())
        session_fraction = min(1.0, session_elapsed_seconds / (375 * 60)) # 375 mins in normal session

        active_states = []
        for state in states.values():
            if state.latest_price <= 0:
                continue

            # 1. Volume Pace
            vol_pace = 0.0
            baseline_vol = state.median_time_volumes.get(market_hhmm)
            if baseline_vol and baseline_vol > 0:
                vol_pace = state.cumulative_volume / baseline_vol
            elif state.adv > 0 and session_fraction > 0:
                # Fallback: Traded Value Pace vs ADV
                expected_value = (state.adv * state.latest_price) * session_fraction
                if expected_value > 0:
                    vol_pace = state.cumulative_value / expected_value

            # 2. Realized Volatility
            realized_vol = 0.0
            if state.rolling_5m_high > 0 and state.rolling_5m_low > 0:
                realized_vol = (state.rolling_5m_high - state.rolling_5m_low) / state.latest_price
            elif state.session_high > 0 and state.session_low > 0:
                realized_vol = (state.session_high - state.session_low) / state.latest_price

            state.volume_pace_percentile = vol_pace
            state.realized_volatility_percentile = realized_vol
            active_states.append(state)

        if not active_states:
            return []

        # Convert to percentiles (0 to 100)
        vols = [s.volume_pace_percentile for s in active_states]
        rvs = [s.realized_volatility_percentile for s in active_states]
        
        # Avoid zero division or nan
        max_vol = max(vols) if vols else 1.0
        max_rv = max(rvs) if rvs else 1.0

        for state in active_states:
            if max_vol > 0:
                state.volume_pace_percentile = (state.volume_pace_percentile / max_vol) * 100.0
            if max_rv > 0:
                state.realized_volatility_percentile = (state.realized_volatility_percentile / max_rv) * 100.0
                
            state.hotness_score = min(state.volume_pace_percentile, state.realized_volatility_percentile)

        # Sort by hotness_score descending
        active_states.sort(key=lambda s: s.hotness_score, reverse=True)

        # Determine new hot set
        current_hot_ids = set()
        for i, state in enumerate(active_states):
            if i < self.top_n:
                current_hot_ids.add(state.security_id)
                if not state.is_hot:
                    state.is_hot = True
                    state.hot_since = int(now)
            else:
                # Check hysteresis
                if state.is_hot and state.hot_since is not None:
                    if now - state.hot_since < self.hysteresis_seconds:
                        current_hot_ids.add(state.security_id)
                    else:
                        state.is_hot = False
                        state.hot_since = None
                else:
                    state.is_hot = False
                    state.hot_since = None

        return [s for s in active_states if s.security_id in current_hot_ids]
