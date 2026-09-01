"""Compact per-instrument state for full-universe live scanning."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dt_time
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple


InstrumentKey = Tuple[str, int]


def optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


@dataclass(frozen=True)
class OHLCV:
    minute_start: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: Optional[float]


@dataclass
class MinuteBuilder:
    minute_start: datetime
    open: float
    high: float
    low: float
    close: float
    starting_volume: float
    ending_volume: float
    vwap: Optional[float]

    def update(self, price: float, volume: float, vwap: Optional[float]) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.ending_volume = max(self.ending_volume, volume)
        if vwap is not None and vwap > 0:
            self.vwap = vwap

    def close_bar(self) -> OHLCV:
        return OHLCV(
            minute_start=self.minute_start.isoformat(),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=max(0.0, self.ending_volume - self.starting_volume),
            vwap=self.vwap,
        )


@dataclass
class LiveStockState:
    exchange_segment: str
    security_id: int
    symbol: str
    isin: str
    previous_close: float = 0.0
    adv_20_cr: float = 0.0
    historical_atr: float = 0.0
    historical_atr_percent: float = 0.0
    median_cumulative_volume: Dict[str, float] = field(default_factory=dict)
    median_range_percent: Dict[str, float] = field(default_factory=dict)
    baseline_interval_minutes: int = 5
    corporate_action: Optional[Dict[str, Any]] = None
    upper_circuit: Optional[float] = None
    lower_circuit: Optional[float] = None

    status: str = "WAITING_FOR_DATA"
    first_packet_at: Optional[str] = None
    last_packet_at: Optional[str] = None
    last_trade_at: Optional[str] = None
    last_trade_quantity: Optional[float] = None
    latest_price: float = 0.0
    previous_price: Optional[float] = None
    cumulative_volume: float = 0.0
    previous_cumulative_volume: Optional[float] = None
    cumulative_value: float = 0.0
    session_vwap: Optional[float] = None
    session_open: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    opening_range_complete: bool = False
    opening_range_source: Optional[str] = None
    depth: List[Dict[str, float]] = field(default_factory=list)
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread_percent: Optional[float] = None
    bid_quantity_5: float = 0.0
    ask_quantity_5: float = 0.0
    depth_imbalance: float = 0.0
    order_count_imbalance: float = 0.0

    price_samples: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=900))
    value_samples: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=900))
    depth_samples: Deque[Tuple[float, float, float]] = field(default_factory=lambda: deque(maxlen=180))
    minute_bars: Deque[OHLCV] = field(default_factory=lambda: deque(maxlen=420))
    minute_builder: Optional[MinuteBuilder] = None
    last_sample_second: Optional[int] = None
    last_depth_second: Optional[int] = None
    last_recorded_second: Optional[int] = None
    session_live_started: bool = False

    volume_pace: Optional[float] = None
    realized_volatility_percent: float = 0.0
    range_pace: Optional[float] = None
    volume_acceleration: Optional[float] = None
    trend_efficiency: float = 0.0
    traded_value_5m: float = 0.0
    return_5m_percent: float = 0.0
    market_return_5m_percent: float = 0.0
    relative_strength_5m_percent: float = 0.0
    relative_strength_percentile: float = 0.0
    volume_percentile: float = 0.0
    volatility_percentile: float = 0.0
    value_percentile: float = 0.0
    hotness: float = 0.0
    activity_rank: Optional[int] = None
    is_hot: bool = False
    hot_until: float = 0.0
    exclusion_reason: Optional[str] = None
    setup_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def key(self) -> InstrumentKey:
        return self.exchange_segment, self.security_id

    @classmethod
    def from_stock(cls, stock: Dict[str, Any]) -> "LiveStockState":
        historical = stock.get("historical") or {}
        baseline = stock.get("intraday_baselines") or {}
        tradability = stock.get("tradability") or {}
        return cls(
            exchange_segment=str(stock["exchange_segment"]).upper(),
            security_id=int(stock["security_id"]),
            symbol=str(stock.get("symbol") or stock.get("trading_symbol") or ""),
            isin=str(stock.get("isin") or ""),
            previous_close=float(historical.get("previous_close") or 0.0),
            adv_20_cr=float(historical.get("adv_20_cr") or 0.0),
            historical_atr=float(historical.get("atr_14") or 0.0),
            historical_atr_percent=float(historical.get("atr_percent") or 0.0),
            median_cumulative_volume=_number_map(baseline.get("median_cumulative_volume")),
            median_range_percent=_number_map(baseline.get("median_range_percent_by_minute")),
            baseline_interval_minutes=max(1, int(baseline.get("interval_minutes") or 5)),
            corporate_action=stock.get("corporate_action"),
            upper_circuit=optional_float(tradability.get("upper_circuit")),
            lower_circuit=optional_float(tradability.get("lower_circuit")),
        )

    def apply_packet(
        self,
        *,
        received_at: datetime,
        price: float,
        cumulative_volume: float,
        vwap: Optional[float],
        last_trade_at: Optional[datetime],
        last_trade_quantity: Optional[float],
        depth: List[Dict[str, float]],
        depth_features: Dict[str, Any],
    ) -> List[OHLCV]:
        now_ts = received_at.timestamp()
        stamp = received_at.isoformat()
        starting_live_session = received_at.time() >= dt_time(9, 15) and not self.session_live_started
        if starting_live_session:
            self.price_samples.clear()
            self.value_samples.clear()
            self.depth_samples.clear()
            self.minute_bars.clear()
            self.minute_builder = None
            self.cumulative_value = cumulative_volume * price
            self.previous_cumulative_volume = cumulative_volume
            self.previous_price = None
            self.session_live_started = True
        self.first_packet_at = self.first_packet_at or stamp
        self.last_packet_at = stamp
        self.previous_price = None if starting_live_session else self.latest_price if self.latest_price > 0 else None
        self.latest_price = price
        if last_trade_at is not None:
            self.last_trade_at = last_trade_at.isoformat()
        if last_trade_quantity is not None:
            self.last_trade_quantity = last_trade_quantity

        if self.previous_cumulative_volume is None:
            self.cumulative_value = cumulative_volume * price
        else:
            if cumulative_volume < self.previous_cumulative_volume:
                self.cumulative_value = cumulative_volume * price
                self.value_samples.clear()
            else:
                self.cumulative_value += max(0.0, cumulative_volume - self.previous_cumulative_volume) * price
        self.previous_cumulative_volume = cumulative_volume
        self.cumulative_volume = cumulative_volume
        if vwap is not None and vwap > 0:
            self.session_vwap = vwap

        self.session_open = self.session_open or price
        self.session_high = price if self.session_high is None else max(self.session_high, price)
        self.session_low = price if self.session_low is None else min(self.session_low, price)
        self._update_opening_range(price, received_at)
        self._sample(now_ts, price)
        self._set_depth(now_ts, depth, depth_features)
        self.status = "HOT" if self.is_hot else "WATCHING"
        return self._update_bar(received_at, price, cumulative_volume, vwap)

    def _sample(self, timestamp: float, price: float) -> None:
        second = int(timestamp)
        sample = (timestamp, price)
        value_sample = (timestamp, self.cumulative_value)
        if self.last_sample_second == second and self.price_samples:
            self.price_samples[-1] = sample
            self.value_samples[-1] = value_sample
        else:
            self.price_samples.append(sample)
            self.value_samples.append(value_sample)
            self.last_sample_second = second

    def _set_depth(self, timestamp: float, depth: List[Dict[str, float]], features: Dict[str, Any]) -> None:
        self.depth = depth
        self.best_bid = optional_float(features.get("best_bid"))
        self.best_ask = optional_float(features.get("best_ask"))
        self.spread_percent = optional_float(features.get("spread_percent"))
        self.bid_quantity_5 = float(features.get("bid_quantity_5") or 0.0)
        self.ask_quantity_5 = float(features.get("ask_quantity_5") or 0.0)
        self.depth_imbalance = float(features.get("depth_imbalance") or 0.0)
        self.order_count_imbalance = float(features.get("order_count_imbalance") or 0.0)
        second = int(timestamp)
        if self.last_depth_second != second:
            self.depth_samples.append((timestamp, self.depth_imbalance, float(self.spread_percent or 0.0)))
            self.last_depth_second = second

    def _update_opening_range(self, price: float, now: datetime) -> None:
        if dt_time(9, 15) <= now.time() < dt_time(9, 30):
            self.opening_range_high = price if self.opening_range_high is None else max(self.opening_range_high, price)
            self.opening_range_low = price if self.opening_range_low is None else min(self.opening_range_low, price)
            self.opening_range_source = "live_feed"
        elif now.time() >= dt_time(9, 30) and self.opening_range_high is not None:
            self.opening_range_complete = True

    def _update_bar(self, now: datetime, price: float, volume: float, vwap: Optional[float]) -> List[OHLCV]:
        minute = now.replace(second=0, microsecond=0)
        if self.minute_builder is None:
            self.minute_builder = MinuteBuilder(minute, price, price, price, price, volume, volume, vwap)
            return []
        if minute <= self.minute_builder.minute_start:
            self.minute_builder.update(price, volume, vwap)
            return []
        bar = self.minute_builder.close_bar()
        self.minute_bars.append(bar)
        self.minute_builder = MinuteBuilder(minute, price, price, price, price, volume, volume, vwap)
        return [bar]

    def refresh_derived(self, now: datetime) -> None:
        now_ts = now.timestamp()
        five_first = five_last = one_first = one_last = one_previous = None
        five_low = five_high = None
        one_path = 0.0
        for timestamp, value in self.price_samples:
            if timestamp >= now_ts - 300:
                five_first = value if five_first is None else five_first
                five_last = value
                five_low = value if five_low is None else min(five_low, value)
                five_high = value if five_high is None else max(five_high, value)
            if timestamp >= now_ts - 60:
                one_first = value if one_first is None else one_first
                one_last = value
                if one_previous is not None:
                    one_path += abs(value - one_previous)
                one_previous = value
        self.realized_volatility_percent = (
            (five_high - five_low) / self.latest_price * 100.0
            if five_high is not None and five_low is not None and self.latest_price > 0
            else 0.0
        )
        self.return_5m_percent = (
            (five_last - five_first) / five_first * 100.0
            if five_first is not None and five_last is not None and five_first > 0
            else 0.0
        )
        expected_range = self._baseline_for_now(self.median_range_percent, now)
        self.range_pace = self.realized_volatility_percent / expected_range if expected_range else None
        expected_volume = self.expected_cumulative_volume(now)
        self.volume_pace = self.cumulative_volume / expected_volume if expected_volume else self._turnover_pace(now)
        windows = (
            [now_ts - 30, now_ts, None, None],
            [now_ts - 150, now_ts - 30, None, None],
            [now_ts - 300, now_ts, None, None],
        )
        for timestamp, value in self.value_samples:
            for window in windows:
                if window[0] <= timestamp <= window[1]:
                    window[2] = value if window[2] is None else window[2]
                    window[3] = value
        recent_value, prior_value, five_minute_value = (
            max(0.0, window[3] - window[2])
            if window[2] is not None and window[3] is not None
            else 0.0
            for window in windows
        )
        self.volume_acceleration = min(8.0, recent_value / (prior_value / 4.0)) if recent_value > 0 and prior_value > 0 else None
        self.trend_efficiency = (
            abs(one_last - one_first) / one_path
            if one_first is not None and one_last is not None and one_path > 0
            else 0.0
        )
        self.traded_value_5m = five_minute_value

    def expected_cumulative_volume(self, now: datetime) -> Optional[float]:
        if not self.median_cumulative_volume:
            return None
        session_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        elapsed = max(0.0, (now - session_start).total_seconds() / 60.0)
        points: List[Tuple[float, float]] = []
        for label, value in self.median_cumulative_volume.items():
            try:
                hour, minute = (int(part) for part in label.split(":", 1))
            except (TypeError, ValueError):
                continue
            bucket_end = (hour * 60 + minute) - (9 * 60 + 15) + self.baseline_interval_minutes
            points.append((float(bucket_end), float(value)))
        points.sort()
        previous_minute, previous_value = 0.0, 0.0
        for point_minute, point_value in points:
            if elapsed <= point_minute:
                fraction = max(0.02, (elapsed - previous_minute) / max(1.0, point_minute - previous_minute))
                return previous_value + max(0.0, point_value - previous_value) * min(1.0, fraction)
            previous_minute, previous_value = point_minute, point_value
        return previous_value or None

    def _turnover_pace(self, now: datetime) -> Optional[float]:
        if self.adv_20_cr <= 0:
            return None
        start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        fraction = min(1.0, max(1.0, (now - start).total_seconds()) / (375.0 * 60.0))
        expected = self.adv_20_cr * 10_000_000.0 * fraction
        return self.cumulative_value / expected if expected > 0 else None

    def _baseline_for_now(self, values: Dict[str, float], now: datetime) -> Optional[float]:
        minute = (now.minute // self.baseline_interval_minutes) * self.baseline_interval_minutes
        value = optional_float(values.get(f"{now.hour:02d}:{minute:02d}"))
        return value if value and value > 0 else None

    def range_percent(self, seconds: int, now_ts: Optional[float] = None) -> float:
        values = self._window(self.price_samples, seconds, now_ts)
        return (max(values) - min(values)) / self.latest_price * 100.0 if values and self.latest_price > 0 else 0.0

    def return_percent(self, seconds: int, now_ts: Optional[float] = None) -> float:
        values = self._window(self.price_samples, seconds, now_ts)
        return (values[-1] - values[0]) / values[0] * 100.0 if len(values) >= 2 and values[0] > 0 else 0.0

    def efficiency(self, seconds: int, now_ts: Optional[float] = None) -> float:
        values = self._window(self.price_samples, seconds, now_ts)
        path = sum(abs(current - previous) for previous, current in zip(values, values[1:]))
        return abs(values[-1] - values[0]) / path if len(values) >= 2 and path > 0 else 0.0

    def value_change(self, seconds: int, now_ts: Optional[float] = None) -> float:
        values = self._window(self.value_samples, seconds, now_ts)
        return max(0.0, values[-1] - values[0]) if len(values) >= 2 else 0.0

    @staticmethod
    def _window(samples: Iterable[Tuple[float, float]], seconds: int, now_ts: Optional[float]) -> List[float]:
        rows = list(samples)
        if not rows:
            return []
        end = float(now_ts if now_ts is not None else rows[-1][0])
        values = [value for timestamp, value in rows if end - seconds <= timestamp <= end]
        return values or [rows[-1][1]]

    def trade_age_seconds(self, now: datetime) -> Optional[float]:
        try:
            return max(0.0, (now - datetime.fromisoformat(str(self.last_trade_at))).total_seconds())
        except (TypeError, ValueError):
            return None

    def depth_median(self, seconds: int, now_ts: float) -> Optional[float]:
        values = sorted(value for timestamp, value, _ in self.depth_samples if timestamp >= now_ts - seconds)
        if not values:
            return None
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2.0

    def feature_snapshot(self, now: datetime) -> Dict[str, Any]:
        return {
            "received_at": self.last_packet_at,
            "last_price": self.latest_price,
            "last_trade_at": self.last_trade_at,
            "last_trade_age_seconds": self.trade_age_seconds(now),
            "day_volume": self.cumulative_volume,
            "vwap": self.session_vwap,
            "opening_range_high": self.opening_range_high,
            "opening_range_low": self.opening_range_low,
            "opening_range_complete": self.opening_range_complete,
            "relative_volume": self.volume_pace,
            "volume_acceleration": self.volume_acceleration,
            "realized_volatility_percent": self.realized_volatility_percent,
            "range_pace": self.range_pace,
            "trend_efficiency": self.trend_efficiency,
            "traded_value_5m": self.traded_value_5m,
            "return_5m_percent": self.return_5m_percent,
            "market_return_5m_percent": self.market_return_5m_percent,
            "relative_strength_5m_percent": self.relative_strength_5m_percent,
            "relative_strength_percentile": self.relative_strength_percentile,
            "spread_percent": self.spread_percent,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "bid_quantity_5": self.bid_quantity_5,
            "ask_quantity_5": self.ask_quantity_5,
            "depth_imbalance": self.depth_imbalance,
            "order_count_imbalance": self.order_count_imbalance,
            "depth_imbalance_median_30s": self.depth_median(30, now.timestamp()),
            "upper_circuit": self.upper_circuit,
            "lower_circuit": self.lower_circuit,
            "volume_pace_percentile": self.volume_percentile,
            "volatility_percentile": self.volatility_percentile,
            "traded_value_percentile": self.value_percentile,
            "hotness_score": self.hotness,
            "activity_rank": self.activity_rank,
            "corporate_action": self.corporate_action,
        }

    def checkpoint(self) -> Dict[str, Any]:
        return {
            "first_packet_at": self.first_packet_at,
            "last_packet_at": self.last_packet_at,
            "last_trade_at": self.last_trade_at,
            "last_trade_quantity": self.last_trade_quantity,
            "latest_price": self.latest_price,
            "previous_price": self.previous_price,
            "cumulative_volume": self.cumulative_volume,
            "previous_cumulative_volume": self.previous_cumulative_volume,
            "cumulative_value": self.cumulative_value,
            "session_vwap": self.session_vwap,
            "session_open": self.session_open,
            "session_high": self.session_high,
            "session_low": self.session_low,
            "opening_range_high": self.opening_range_high,
            "opening_range_low": self.opening_range_low,
            "opening_range_complete": self.opening_range_complete,
            "opening_range_source": self.opening_range_source,
            "session_live_started": self.session_live_started,
            "price_samples": list(self.price_samples)[-300:],
            "value_samples": list(self.value_samples)[-300:],
            "depth_samples": list(self.depth_samples)[-60:],
            "minute_bars": [asdict(bar) for bar in list(self.minute_bars)[-60:]],
            "setup_state": self.setup_state,
        }

    def restore(self, payload: Dict[str, Any]) -> None:
        for name in (
            "first_packet_at", "last_packet_at", "last_trade_at", "last_trade_quantity",
            "latest_price", "previous_price", "cumulative_volume", "previous_cumulative_volume",
            "cumulative_value", "session_vwap", "session_open", "session_high", "session_low",
            "opening_range_high", "opening_range_low", "opening_range_complete",
            "opening_range_source", "setup_state",
            "session_live_started",
        ):
            if name in payload:
                setattr(self, name, payload[name])
        self.price_samples = deque(_tuples(payload.get("price_samples"), 2), maxlen=900)
        self.value_samples = deque(_tuples(payload.get("value_samples"), 2), maxlen=900)
        self.depth_samples = deque(_tuples(payload.get("depth_samples"), 3), maxlen=180)
        self.minute_bars = deque(
            (OHLCV(**row) for row in payload.get("minute_bars") or [] if isinstance(row, dict)),
            maxlen=420,
        )


def _number_map(values: Any) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for key, value in (values or {}).items():
        number = optional_float(value)
        if number is not None and number >= 0:
            result[str(key)] = number
    return result


def _tuples(values: Any, length: int) -> Iterable[tuple]:
    for value in values or []:
        if isinstance(value, (list, tuple)) and len(value) == length:
            yield tuple(float(item) for item in value)

