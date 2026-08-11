"""Causal one-minute indicator and candlestick event detection.

The engine deliberately detects *new transitions* on completed candles.  It
does not decide whether a stock should be traded; it produces compact evidence
for the stock AI agent to investigate.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Deque, Dict, Iterable, List


class IndicatorEventEngine:
    # Preserve one complete cash-market session so the readiness layer can use
    # slower five- and fifteen-minute structure.
    BAR_LIMIT = 420

    def __init__(
        self,
        *,
        fast_ema_period: int = 9,
        slow_ema_period: int = 21,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        volume_surge_ratio: float = 1.8,
        event_cooldown_seconds: int = 600,
        max_event_lag_seconds: int = 60,
    ) -> None:
        self.fast_ema_period = fast_ema_period
        self.slow_ema_period = slow_ema_period
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.volume_surge_ratio = volume_surge_ratio
        self.event_cooldown_seconds = event_cooldown_seconds
        self.max_event_lag_seconds = max_event_lag_seconds

    @staticmethod
    def state_fields() -> Dict[str, Any]:
        return {
            "minute_builder": None,
            "minute_bars": deque(maxlen=IndicatorEventEngine.BAR_LIMIT),
            "last_closed_cumulative_volume": None,
            "indicator_snapshot": {},
            "indicator_event_last_at": {},
            "pending_indicator_events": [],
            "pending_indicator_deadline": None,
            "pending_indicator_generation": 0,
        }

    @staticmethod
    def _minute_start(timestamp: datetime) -> datetime:
        return timestamp.replace(second=0, microsecond=0)

    @staticmethod
    def _new_builder(
        timestamp: datetime,
        price: float,
        cumulative_volume: float,
        vwap: float | None,
    ) -> Dict[str, Any]:
        return {
            "minute_start": IndicatorEventEngine._minute_start(timestamp).isoformat(),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "cumulative_volume": cumulative_volume,
            "vwap": vwap,
            "last_received_at": timestamp.isoformat(),
        }

    @staticmethod
    def _update_builder(
        builder: Dict[str, Any],
        timestamp: datetime,
        price: float,
        cumulative_volume: float,
        vwap: float | None,
    ) -> None:
        builder["high"] = max(float(builder["high"]), price)
        builder["low"] = min(float(builder["low"]), price)
        builder["close"] = price
        builder["cumulative_volume"] = max(
            float(builder.get("cumulative_volume") or 0.0), cumulative_volume
        )
        if vwap is not None and vwap > 0:
            builder["vwap"] = vwap
        builder["last_received_at"] = timestamp.isoformat()

    @staticmethod
    def _ema(values: Iterable[float], period: int) -> float | None:
        sequence = list(values)
        if len(sequence) < period:
            return None
        alpha = 2.0 / (period + 1.0)
        value = sum(sequence[:period]) / period
        for item in sequence[period:]:
            value = alpha * item + (1.0 - alpha) * value
        return value

    @staticmethod
    def _rsi(values: Iterable[float], period: int) -> float | None:
        closes = list(values)
        if len(closes) < period + 1:
            return None
        deltas = [current - previous for previous, current in zip(closes, closes[1:])]
        gains = [max(0.0, value) for value in deltas]
        losses = [max(0.0, -value) for value in deltas]
        average_gain = sum(gains[:period]) / period
        average_loss = sum(losses[:period]) / period
        for gain, loss in zip(gains[period:], losses[period:]):
            average_gain = ((period - 1) * average_gain + gain) / period
            average_loss = ((period - 1) * average_loss + loss) / period
        if average_loss == 0:
            return 100.0 if average_gain > 0 else 50.0
        strength = average_gain / average_loss
        return 100.0 - (100.0 / (1.0 + strength))

    @staticmethod
    def _atr(bars: List[Dict[str, Any]], period: int = 14) -> float | None:
        if len(bars) < 2:
            return None
        ranges = []
        for previous, current in zip(bars, bars[1:]):
            previous_close = float(previous["close"])
            ranges.append(
                max(
                    float(current["high"]) - float(current["low"]),
                    abs(float(current["high"]) - previous_close),
                    abs(float(current["low"]) - previous_close),
                )
            )
        sample = ranges[-period:]
        return sum(sample) / len(sample) if sample else None

    @staticmethod
    def _patterns(current: Dict[str, Any], previous: Dict[str, Any] | None) -> List[Dict[str, Any]]:
        open_price = float(current["open"])
        high = float(current["high"])
        low = float(current["low"])
        close = float(current["close"])
        candle_range = max(0.0, high - low)
        body = abs(close - open_price)
        body_floor = max(body, candle_range * 0.05, 1e-9)
        upper_wick = max(0.0, high - max(open_price, close))
        lower_wick = max(0.0, min(open_price, close) - low)
        events: List[Dict[str, Any]] = []
        if candle_range > 0 and body / candle_range <= 0.12:
            events.append({"event_type": "DOJI", "direction": "NEUTRAL"})
        if (
            candle_range > 0
            and lower_wick >= 2.0 * body_floor
            and upper_wick <= body_floor
            and close >= low + candle_range * 0.60
        ):
            events.append({"event_type": "HAMMER", "direction": "LONG"})
        if (
            candle_range > 0
            and upper_wick >= 2.0 * body_floor
            and lower_wick <= body_floor
            and close <= low + candle_range * 0.40
        ):
            events.append({"event_type": "SHOOTING_STAR", "direction": "SHORT"})
        if previous is not None:
            previous_open = float(previous["open"])
            previous_close = float(previous["close"])
            if (
                close > open_price
                and previous_close < previous_open
                and open_price <= previous_close
                and close >= previous_open
            ):
                events.append({"event_type": "BULLISH_ENGULFING", "direction": "LONG"})
            if (
                close < open_price
                and previous_close > previous_open
                and open_price >= previous_close
                and close <= previous_open
            ):
                events.append({"event_type": "BEARISH_ENGULFING", "direction": "SHORT"})
        return events

    def _allowed(self, state: Dict[str, Any], event_type: str, detected_at: datetime) -> bool:
        last_at = (state.get("indicator_event_last_at") or {}).get(event_type)
        if last_at:
            try:
                if detected_at - datetime.fromisoformat(str(last_at)) < timedelta(
                    seconds=self.event_cooldown_seconds
                ):
                    return False
            except ValueError:
                pass
        state.setdefault("indicator_event_last_at", {})[event_type] = detected_at.isoformat()
        return True

    def _detect(
        self,
        state: Dict[str, Any],
        bar: Dict[str, Any],
        detected_at: datetime,
        opening_range_high: float | None,
        opening_range_low: float | None,
        opening_range_complete: bool,
    ) -> List[Dict[str, Any]]:
        bars = list(state.get("minute_bars") or [])
        previous_bar = bars[-2] if len(bars) >= 2 else None
        closes = [float(item["close"]) for item in bars]
        fast_ema = self._ema(closes, self.fast_ema_period)
        slow_ema = self._ema(closes, self.slow_ema_period)
        rsi = self._rsi(closes, self.rsi_period)
        atr = self._atr(bars)
        previous_snapshot = state.get("indicator_snapshot") or {}
        previous_fast = previous_snapshot.get("ema_fast")
        previous_slow = previous_snapshot.get("ema_slow")
        previous_rsi = previous_snapshot.get("rsi")
        prior_volumes = [
            float(item.get("volume") or 0.0)
            for item in bars[-11:-1]
            if float(item.get("volume") or 0.0) > 0
        ]
        normal_volume = median(prior_volumes) if len(prior_volumes) >= 5 else None
        volume_ratio = (
            float(bar.get("volume") or 0.0) / normal_volume
            if normal_volume and normal_volume > 0
            else None
        )
        candidates: List[Dict[str, Any]] = []
        try:
            expected_close = datetime.fromisoformat(str(bar["minute_start"])) + timedelta(minutes=1)
            event_is_fresh = (
                detected_at - expected_close
            ).total_seconds() <= self.max_event_lag_seconds
        except (KeyError, TypeError, ValueError):
            event_is_fresh = False

        def add(event_type: str, direction: str, **details: Any) -> None:
            if not event_is_fresh:
                return
            if not self._allowed(state, event_type, detected_at):
                return
            candidates.append(
                {
                    "event_type": event_type,
                    "direction": direction,
                    "detected_at": detected_at.isoformat(),
                    "bar_start": bar["minute_start"],
                    "timeframe": "1m",
                    "price": round(float(bar["close"]), 4),
                    "details": details,
                }
            )

        if all(value is not None for value in (previous_fast, previous_slow, fast_ema, slow_ema)):
            previous_difference = float(previous_fast) - float(previous_slow)
            current_difference = float(fast_ema) - float(slow_ema)
            if previous_difference <= 0 < current_difference:
                add("EMA_BULLISH_CROSS", "LONG", ema_fast=fast_ema, ema_slow=slow_ema)
            elif previous_difference >= 0 > current_difference:
                add("EMA_BEARISH_CROSS", "SHORT", ema_fast=fast_ema, ema_slow=slow_ema)

        if previous_rsi is not None and rsi is not None:
            if float(previous_rsi) >= self.rsi_oversold > rsi:
                add("RSI_ENTERED_OVERSOLD", "NEUTRAL", rsi=rsi, threshold=self.rsi_oversold)
            if float(previous_rsi) <= self.rsi_overbought < rsi:
                add("RSI_ENTERED_OVERBOUGHT", "NEUTRAL", rsi=rsi, threshold=self.rsi_overbought)
            if float(previous_rsi) <= self.rsi_oversold < rsi:
                add("RSI_EXITED_OVERSOLD", "LONG", rsi=rsi, threshold=self.rsi_oversold)
            if float(previous_rsi) >= self.rsi_overbought > rsi:
                add("RSI_EXITED_OVERBOUGHT", "SHORT", rsi=rsi, threshold=self.rsi_overbought)

        detected_patterns = self._patterns(bar, previous_bar)
        for pattern in detected_patterns:
            add(
                str(pattern["event_type"]),
                str(pattern["direction"]),
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
            )

        if previous_bar is not None:
            previous_vwap = previous_bar.get("vwap")
            current_vwap = bar.get("vwap")
            if previous_vwap and current_vwap:
                if float(previous_bar["close"]) <= float(previous_vwap) < float(bar["close"]):
                    add("VWAP_BULLISH_CROSS", "LONG", vwap=current_vwap)
                elif float(previous_bar["close"]) >= float(previous_vwap) > float(bar["close"]):
                    add("VWAP_BEARISH_CROSS", "SHORT", vwap=current_vwap)
            if opening_range_complete and opening_range_high and opening_range_low:
                if float(previous_bar["close"]) <= opening_range_high < float(bar["close"]):
                    add("ORB_BULLISH_CLOSE_BREAK", "LONG", level=opening_range_high)
                elif float(previous_bar["close"]) >= opening_range_low > float(bar["close"]):
                    add("ORB_BEARISH_CLOSE_BREAK", "SHORT", level=opening_range_low)

        if volume_ratio is not None and volume_ratio >= self.volume_surge_ratio:
            candle_range = max(1e-9, float(bar["high"]) - float(bar["low"]))
            signed_body = float(bar["close"]) - float(bar["open"])
            body_to_range = abs(signed_body) / candle_range
            close_location = (float(bar["close"]) - float(bar["low"])) / candle_range
            # Volume is participation, not direction.  It becomes directional
            # only when a completed candle also closes decisively near one end.
            candle_direction = "NEUTRAL"
            if body_to_range >= 0.35 and close_location >= 0.70:
                candle_direction = "LONG"
            elif body_to_range >= 0.35 and close_location <= 0.30:
                candle_direction = "SHORT"
            add(
                "VOLUME_SURGE",
                candle_direction,
                volume_ratio=volume_ratio,
                median_prior_volume=normal_volume,
                current_volume=float(bar.get("volume") or 0.0),
                body_to_range=body_to_range,
                close_location=close_location,
                baseline_samples=len(prior_volumes),
            )

        state["indicator_snapshot"] = {
            "as_of": detected_at.isoformat(),
            "bar_start": bar["minute_start"],
            "close": round(float(bar["close"]), 4),
            "ema_fast": round(fast_ema, 6) if fast_ema is not None else None,
            "ema_slow": round(slow_ema, 6) if slow_ema is not None else None,
            "rsi": round(rsi, 4) if rsi is not None else None,
            "atr": round(atr, 6) if atr is not None else None,
            "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
            # Snapshot describes the closed candle even when an equivalent event
            # was suppressed by its cooldown.
            "patterns": [item["event_type"] for item in detected_patterns],
        }
        return candidates

    def on_tick(
        self,
        state: Dict[str, Any],
        *,
        timestamp: datetime,
        price: float,
        cumulative_volume: float,
        vwap: float | None,
        opening_range_high: float | None,
        opening_range_low: float | None,
        opening_range_complete: bool,
    ) -> List[Dict[str, Any]]:
        """Update the current minute and return events from a newly closed bar."""
        minute_start = self._minute_start(timestamp)
        builder = state.get("minute_builder")
        if not builder:
            state["minute_builder"] = self._new_builder(
                timestamp, price, cumulative_volume, vwap
            )
            return []
        builder_start = datetime.fromisoformat(str(builder["minute_start"]))
        if minute_start <= builder_start:
            self._update_builder(builder, timestamp, price, cumulative_volume, vwap)
            return []

        previous_cumulative = float(state.get("last_closed_cumulative_volume") or 0.0)
        ending_cumulative = float(builder.get("cumulative_volume") or 0.0)
        bar = {
            **builder,
            "volume": max(0.0, ending_cumulative - previous_cumulative)
            if previous_cumulative > 0
            else 0.0,
        }
        state["last_closed_cumulative_volume"] = ending_cumulative
        events = self.on_closed_bar(
            state,
            bar=bar,
            detected_at=timestamp,
            opening_range_high=opening_range_high,
            opening_range_low=opening_range_low,
            opening_range_complete=opening_range_complete,
        )
        state["minute_builder"] = self._new_builder(
            timestamp, price, cumulative_volume, vwap
        )
        return events

    def on_closed_bar(
        self,
        state: Dict[str, Any],
        *,
        bar: Dict[str, Any],
        detected_at: datetime,
        opening_range_high: float | None,
        opening_range_low: float | None,
        opening_range_complete: bool,
    ) -> List[Dict[str, Any]]:
        """Process one already-closed causal bar.

        Production uses this through :meth:`on_tick`. Recorded-session replay
        uses the same method after constructing minute OHLCV from saved ticks,
        so research does not need a second copy of the indicator rules.
        """
        bars: Deque[Dict[str, Any]] = state.get("minute_bars")
        if not isinstance(bars, deque):
            bars = deque(bars or [], maxlen=self.BAR_LIMIT)
            state["minute_bars"] = bars
        bars.append(dict(bar))
        return self._detect(
            state,
            dict(bar),
            detected_at,
            opening_range_high,
            opening_range_low,
            opening_range_complete,
        )
