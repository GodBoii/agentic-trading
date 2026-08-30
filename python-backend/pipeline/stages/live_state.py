from dataclasses import dataclass, field
from collections import deque
from typing import Dict, List, Optional

@dataclass
class OHLCV:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class LiveStockState:
    security_id: int
    exchange_segment: str
    symbol: str
    
    # Real-time packet fields
    latest_price: float = 0.0
    exchange_time: int = 0
    cumulative_volume: int = 0
    cumulative_value: float = 0.0
    session_vwap: float = 0.0
    
    # Depth: {'bids': [(price, qty, orders), ...], 'asks': [...]}
    depth: Dict[str, List] = field(default_factory=lambda: {'bids': [], 'asks': []})
    
    # Pre-calculated baselines
    adv: float = 0.0
    historical_atr: float = 0.0
    median_time_volumes: Dict[str, int] = field(default_factory=dict) # HH:MM -> volume
    
    # Session tracking
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    previous_close: float = 0.0
    session_high: float = 0.0
    session_low: float = 0.0
    
    # Short-term history
    recent_bars: deque = field(default_factory=lambda: deque(maxlen=20)) # 1-min bars
    rolling_1m_high: float = 0.0
    rolling_1m_low: float = 0.0
    rolling_5m_high: float = 0.0
    rolling_5m_low: float = 0.0
    
    # Ranker output fields
    volume_pace_percentile: float = 0.0
    realized_volatility_percentile: float = 0.0
    hotness_score: float = 0.0
    is_hot: bool = False
    hot_since: Optional[int] = None

    def update_session_extremes(self, price: float):
        if self.session_high == 0.0 or price > self.session_high:
            self.session_high = price
        if self.session_low == 0.0 or price < self.session_low:
            self.session_low = price
