"""Conservative, causal trade-readiness scoring for Stage 2.

Indicator events are observations, not trade setups.  This module combines
completed intraday candles with location, participation, and execution quality
to decide whether an observation is mature enough for an AI-agent review.

The implementation is deliberately deterministic and uses only information
available at the evaluation timestamp.  It does not render charts and it does
not look at future candles.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


READINESS_SCHEMA_VERSION = 1


def indicator_event_lifetime_seconds(event_type: str) -> int:
    """How long an observation remains relevant to a slower intraday setup."""
    if event_type.startswith("ORB_") or event_type.startswith("EMA_"):
        return 600
    if event_type.startswith("VWAP_"):
        return 300
    if event_type == "VOLUME_SURGE":
        return 180
    return 300


def fresh_indicator_events(
    events: Sequence[Dict[str, Any]],
    evaluated_at: datetime,
) -> List[Dict[str, Any]]:
    """Remove expired evidence and keep only the newest event of each type."""
    newest: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}
    for item in events:
        event_type = str(item.get("event_type") or "")
        try:
            detected_at = datetime.fromisoformat(str(item.get("detected_at")))
            age = max(0.0, (evaluated_at - detected_at).total_seconds())
        except (TypeError, ValueError):
            continue
        if age > indicator_event_lifetime_seconds(event_type):
            continue
        previous = newest.get(event_type)
        if previous is None or detected_at > previous[0]:
            newest[event_type] = (detected_at, item)
    return [item for _, item in sorted(newest.values(), key=lambda value: value[0])]


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _ema(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _atr(bars: Sequence[Dict[str, float]], period: int = 14) -> Optional[float]:
    if len(bars) < 2:
        return None
    ranges: List[float] = []
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


def _parse_bars(raw_bars: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bars: List[Dict[str, Any]] = []
    for raw in raw_bars:
        try:
            timestamp = datetime.fromisoformat(str(raw["minute_start"]))
            item = {
                "timestamp": timestamp,
                "minute_start": timestamp.isoformat(),
                "open": float(raw["open"]),
                "high": float(raw["high"]),
                "low": float(raw["low"]),
                "close": float(raw["close"]),
                "volume": max(0.0, float(raw.get("volume") or 0.0)),
                "vwap": _number(raw.get("vwap")),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if item["high"] < item["low"] or not (
            item["low"] <= item["open"] <= item["high"]
            and item["low"] <= item["close"] <= item["high"]
        ):
            continue
        bars.append(item)
    bars.sort(key=lambda item: item["timestamp"])
    return bars


def _aggregate(bars: Sequence[Dict[str, Any]], minutes: int) -> List[Dict[str, Any]]:
    grouped: List[Dict[str, Any]] = []
    current_key: Optional[Tuple[Any, int]] = None
    current: Optional[Dict[str, Any]] = None
    for bar in bars:
        timestamp: datetime = bar["timestamp"]
        minute_of_day = timestamp.hour * 60 + timestamp.minute
        bucket_minute = (minute_of_day // minutes) * minutes
        key = (timestamp.date(), bucket_minute)
        if key != current_key:
            if current is not None:
                grouped.append(current)
            current_key = key
            current = {
                "timestamp": timestamp.replace(
                    hour=bucket_minute // 60,
                    minute=bucket_minute % 60,
                    second=0,
                    microsecond=0,
                ),
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": float(bar["volume"]),
                "vwap": bar.get("vwap"),
                "source_bar_count": 1,
            }
        else:
            assert current is not None
            current["high"] = max(float(current["high"]), float(bar["high"]))
            current["low"] = min(float(current["low"]), float(bar["low"]))
            current["close"] = float(bar["close"])
            current["volume"] = float(current["volume"]) + float(bar["volume"])
            current["source_bar_count"] = int(current["source_bar_count"]) + 1
            if bar.get("vwap") is not None:
                current["vwap"] = bar["vwap"]
    if current is not None:
        grouped.append(current)
    return grouped


def _cluster_levels(levels: Iterable[float], tolerance: float) -> List[float]:
    ordered = sorted(value for value in levels if value > 0)
    clusters: List[List[float]] = []
    for value in ordered:
        if clusters and abs(value - median(clusters[-1])) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [float(median(cluster)) for cluster in clusters]


def _structure_levels(
    bars_5m: Sequence[Dict[str, Any]],
    *,
    price: float,
    atr: float,
    vwap: Optional[float],
    opening_range_high: Optional[float],
    opening_range_low: Optional[float],
    previous_close: Optional[float],
) -> Dict[str, Any]:
    raw_levels: List[float] = []
    recent = list(bars_5m[-48:])
    for index in range(2, len(recent) - 2):
        current = recent[index]
        neighbours = recent[index - 2 : index] + recent[index + 1 : index + 3]
        if float(current["low"]) <= min(float(item["low"]) for item in neighbours):
            raw_levels.append(float(current["low"]))
        if float(current["high"]) >= max(float(item["high"]) for item in neighbours):
            raw_levels.append(float(current["high"]))
    # Exclude the two newest five-minute bars from session extremes.  Their
    # current high/low is still forming the move being evaluated and must not be
    # mistaken for established resistance/support.
    established = recent[:-2]
    if established:
        raw_levels.extend(
            [
                min(float(item["low"]) for item in established),
                max(float(item["high"]) for item in established),
            ]
        )
    raw_levels.extend(
        value
        for value in (vwap, opening_range_high, opening_range_low, previous_close)
        if value is not None and value > 0
    )
    tolerance = max(atr * 0.15, price * 0.0005)
    levels = _cluster_levels(raw_levels, tolerance)
    supports = [value for value in levels if value < price - price * 0.0001]
    resistances = [value for value in levels if value > price + price * 0.0001]
    return {
        "levels": levels,
        "nearest_support": max(supports) if supports else None,
        "nearest_resistance": min(resistances) if resistances else None,
    }


def _aligned(value: float, direction: str) -> bool:
    return value > 0 if direction == "LONG" else value < 0


def _event_confirmation_score(
    events: Sequence[Dict[str, Any]],
    *,
    direction: str,
    near_supportive_level: bool,
) -> Tuple[float, List[str]]:
    weights = {
        "ORB_BULLISH_CLOSE_BREAK": 8.0,
        "ORB_BEARISH_CLOSE_BREAK": 8.0,
        "VWAP_BULLISH_CROSS": 6.0,
        "VWAP_BEARISH_CROSS": 6.0,
        "EMA_BULLISH_CROSS": 6.0,
        "EMA_BEARISH_CROSS": 6.0,
        "BULLISH_ENGULFING": 4.0,
        "BEARISH_ENGULFING": 4.0,
        "RSI_EXITED_OVERSOLD": 3.0,
        "RSI_EXITED_OVERBOUGHT": 3.0,
        "HAMMER": 2.0,
        "SHOOTING_STAR": 2.0,
    }
    accepted: List[Tuple[float, str]] = []
    for event in events:
        if str(event.get("direction") or "NEUTRAL") != direction:
            continue
        event_type = str(event.get("event_type") or "")
        weight = weights.get(event_type, 0.0)
        if event_type in {
            "HAMMER",
            "SHOOTING_STAR",
            "BULLISH_ENGULFING",
            "BEARISH_ENGULFING",
        } and not near_supportive_level:
            weight *= 0.35
        if weight > 0:
            accepted.append((weight, event_type))
    accepted.sort(reverse=True)
    # Several names for the same one-minute candle must not overwhelm structure.
    score = sum(weight for weight, _ in accepted[:2])
    return min(10.0, score), [event_type for _, event_type in accepted]


def _candidate(
    direction: str,
    *,
    bars_1m: Sequence[Dict[str, Any]],
    bars_5m: Sequence[Dict[str, Any]],
    bars_15m: Sequence[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
    features: Dict[str, Any],
    levels: Dict[str, Any],
    atr: float,
    threshold: float,
    min_room_atr: float,
    max_last_trade_age_seconds: int,
    min_confirmation_seconds: int,
    max_entry_drift_atr: float,
) -> Dict[str, Any]:
    price = float(features["last_price"])
    sign = 1.0 if direction == "LONG" else -1.0
    vwap = _number(features.get("vwap"))
    nearest_support = _number(levels.get("nearest_support"))
    nearest_resistance = _number(levels.get("nearest_resistance"))
    supportive = nearest_support if direction == "LONG" else nearest_resistance
    opposing = nearest_resistance if direction == "LONG" else nearest_support
    supportive_distance = (
        abs(price - supportive) / atr if supportive is not None else None
    )
    room = (
        (opposing - price) if direction == "LONG" and opposing is not None else
        (price - opposing) if direction == "SHORT" and opposing is not None else
        atr * 1.5
    )
    room_atr = max(0.0, room / atr)
    near_supportive = supportive_distance is not None and supportive_distance <= 0.45

    closes_5m = [float(item["close"]) for item in bars_5m]
    # Four/nine EMA on completed 5m bars represents roughly 20/45 minutes and
    # becomes available after the opening warm-up without falling back to 1m
    # crossover noise.
    ema_fast = _ema(closes_5m, 4)
    ema_slow = _ema(closes_5m, 9)
    structure = 0.0
    if vwap is not None:
        structure += 8.0 if _aligned((price - vwap) * sign, "LONG") else -4.0
    if ema_fast is not None and ema_slow is not None:
        structure += 10.0 if (ema_fast - ema_slow) * sign > 0 else -6.0
    if len(bars_15m) >= 3:
        slope_15m = (float(bars_15m[-1]["close"]) - float(bars_15m[-3]["close"])) / atr
        structure += 8.0 if slope_15m * sign > 0.12 else (-4.0 if slope_15m * sign < -0.12 else 2.0)
    else:
        slope_15m = None
    if len(closes_5m) >= 3:
        progress = (closes_5m[-1] - closes_5m[-3]) * sign
        structure += 4.0 if progress > 0 else 0.0
    structure = min(30.0, max(0.0, structure))

    location = 0.0
    if room_atr >= 1.5:
        location += 12.0
    elif room_atr >= 1.0:
        location += 9.0
    elif room_atr >= 0.70:
        location += 6.0
    elif room_atr >= min_room_atr:
        location += 3.0
    if near_supportive:
        location += 6.0

    event_types = {str(item.get("event_type") or "") for item in events}
    long_structure_types = {
        "ORB_BULLISH_CLOSE_BREAK",
        "VWAP_BULLISH_CROSS",
        "EMA_BULLISH_CROSS",
    }
    short_structure_types = {
        "ORB_BEARISH_CLOSE_BREAK",
        "VWAP_BEARISH_CROSS",
        "EMA_BEARISH_CROSS",
    }
    long_pattern_types = {"HAMMER", "BULLISH_ENGULFING"}
    short_pattern_types = {"SHOOTING_STAR", "BEARISH_ENGULFING"}
    aligned_structure_types = long_structure_types if direction == "LONG" else short_structure_types
    aligned_pattern_types = long_pattern_types if direction == "LONG" else short_pattern_types
    aligned_rsi_exit = (
        "RSI_EXITED_OVERSOLD" if direction == "LONG" else "RSI_EXITED_OVERBOUGHT"
    )
    directional_volume = any(
        str(item.get("event_type") or "") == "VOLUME_SURGE"
        and str(item.get("direction") or "NEUTRAL") == direction
        for item in events
    )
    has_primary_catalyst = bool(event_types & aligned_structure_types) or bool(
        event_types & aligned_pattern_types
        and (aligned_rsi_exit in event_types or directional_volume)
    )
    recent_closes = [float(item["close"]) for item in bars_1m[-3:]]
    opening_high = _number(features.get("opening_range_high"))
    opening_low = _number(features.get("opening_range_low"))
    breakout_accepted = False
    if direction == "LONG" and "ORB_BULLISH_CLOSE_BREAK" in event_types and opening_high:
        breakout_accepted = len(recent_closes) >= 2 and all(value > opening_high for value in recent_closes[-2:])
    elif direction == "SHORT" and "ORB_BEARISH_CLOSE_BREAK" in event_types and opening_low:
        breakout_accepted = len(recent_closes) >= 2 and all(value < opening_low for value in recent_closes[-2:])
    elif vwap is not None and (
        (direction == "LONG" and "VWAP_BULLISH_CROSS" in event_types)
        or (direction == "SHORT" and "VWAP_BEARISH_CROSS" in event_types)
    ):
        breakout_accepted = len(recent_closes) >= 2 and all(
            (value - vwap) * sign > 0 for value in recent_closes[-2:]
        )
    if breakout_accepted:
        location += 7.0
    location = min(25.0, location)

    event_score, directional_events = _event_confirmation_score(
        events,
        direction=direction,
        near_supportive_level=near_supportive,
    )
    relevant_events = [
        item for item in events if str(item.get("direction") or "NEUTRAL") == direction
    ]
    opposite = "SHORT" if direction == "LONG" else "LONG"
    opposite_score, opposite_events = _event_confirmation_score(
        events,
        direction=opposite,
        near_supportive_level=False,
    )
    evaluated_at: Optional[datetime]
    try:
        evaluated_at = datetime.fromisoformat(str(features.get("received_at")))
    except (TypeError, ValueError):
        evaluated_at = None
    evidence_ages = []
    event_prices = []
    for item in relevant_events:
        try:
            if evaluated_at is not None:
                evidence_ages.append(
                    max(
                        0.0,
                        (evaluated_at - datetime.fromisoformat(str(item.get("detected_at")))).total_seconds(),
                    )
                )
        except (TypeError, ValueError):
            pass
        event_price = _number(item.get("price"))
        if event_price is not None and event_price > 0:
            event_prices.append(event_price)
    confirmation_age = max(evidence_ages) if evidence_ages else None
    reference_event_price = float(median(event_prices)) if event_prices else None
    entry_drift_atr = (
        (price - reference_event_price) * sign / atr
        if reference_event_price is not None
        else None
    )

    complete_5m = [item for item in bars_5m if int(item.get("source_bar_count") or 0) >= 5]
    complete_closes_5m = [float(item["close"]) for item in complete_5m]
    setup_confirmed = False
    if direction == "LONG" and "ORB_BULLISH_CLOSE_BREAK" in event_types and opening_high:
        setup_confirmed = len(complete_closes_5m) >= 2 and all(
            value > opening_high for value in complete_closes_5m[-2:]
        )
    elif direction == "SHORT" and "ORB_BEARISH_CLOSE_BREAK" in event_types and opening_low:
        setup_confirmed = len(complete_closes_5m) >= 2 and all(
            value < opening_low for value in complete_closes_5m[-2:]
        )
    elif vwap is not None and (
        (direction == "LONG" and "VWAP_BULLISH_CROSS" in event_types)
        or (direction == "SHORT" and "VWAP_BEARISH_CROSS" in event_types)
    ):
        setup_confirmed = len(complete_closes_5m) >= 2 and all(
            (value - vwap) * sign > 0 for value in complete_closes_5m[-2:]
        )
    elif (
        (direction == "LONG" and "EMA_BULLISH_CROSS" in event_types)
        or (direction == "SHORT" and "EMA_BEARISH_CROSS" in event_types)
    ):
        setup_confirmed = (
            ema_fast is not None
            and ema_slow is not None
            and (ema_fast - ema_slow) * sign > 0
            and len(complete_closes_5m) >= 2
            and (complete_closes_5m[-1] - complete_closes_5m[-2]) * sign > 0
        )
    elif any(
        event_type in event_types
        for event_type in (
            "BULLISH_ENGULFING" if direction == "LONG" else "BEARISH_ENGULFING",
            "HAMMER" if direction == "LONG" else "SHOOTING_STAR",
            "RSI_EXITED_OVERSOLD" if direction == "LONG" else "RSI_EXITED_OVERBOUGHT",
        )
    ):
        if complete_5m:
            latest = complete_5m[-1]
            setup_confirmed = near_supportive and (
                (float(latest["close"]) - float(latest["open"])) * sign > 0
            )

    confirmation = event_score + (10.0 if setup_confirmed else 0.0)
    if setup_confirmed and len(recent_closes) >= 3:
        directional_closes = sum(
            1
            for previous, current in zip(recent_closes, recent_closes[1:])
            if (current - previous) * sign > 0
        )
        confirmation += 5.0 if directional_closes == 2 else (2.0 if directional_closes == 1 else 0.0)
    last_bar = bars_1m[-1]
    candle_range = max(1e-9, float(last_bar["high"]) - float(last_bar["low"]))
    directional_body = (float(last_bar["close"]) - float(last_bar["open"])) * sign
    if setup_confirmed and directional_body / candle_range >= 0.35:
        confirmation += 5.0
    confirmation = min(20.0, confirmation)

    rvol = _number(features.get("relative_volume"))
    acceleration = _number(features.get("volume_acceleration"))
    volumes_5m = [float(item["volume"]) for item in bars_5m]
    recent_volume_ratio: Optional[float] = None
    if len(volumes_5m) >= 5:
        normal = median(value for value in volumes_5m[-5:-1] if value > 0) if any(
            value > 0 for value in volumes_5m[-5:-1]
        ) else 0.0
        if normal > 0:
            recent_volume_ratio = volumes_5m[-1] / normal
    participation = 0.0
    if rvol is not None:
        participation += 6.0 if rvol >= 1.5 else 5.0 if rvol >= 1.2 else 4.0 if rvol >= 1.0 else 2.0 if rvol >= 0.8 else 0.0
    if acceleration is not None:
        participation += 3.0 if acceleration >= 1.5 else 2.0 if acceleration >= 1.15 else 1.0 if acceleration >= 0.9 else 0.0
    if recent_volume_ratio is not None:
        participation += 4.0 if recent_volume_ratio >= 1.8 else 3.0 if recent_volume_ratio >= 1.3 else 2.0 if recent_volume_ratio >= 1.0 else 1.0 if recent_volume_ratio >= 0.75 else 0.0
    last_trade_age = _number(features.get("last_trade_age_seconds"))
    if last_trade_age is None:
        # Old recordings do not contain LTT.  Absence is reported, but does not
        # make historical replay look fresher than it was.
        trade_freshness_points = 0.0
    elif last_trade_age <= 15:
        trade_freshness_points = 2.0
    elif last_trade_age <= max_last_trade_age_seconds:
        trade_freshness_points = 1.0
    else:
        trade_freshness_points = 0.0
    participation = min(15.0, participation + trade_freshness_points)

    spread = _number(features.get("spread_percent"))
    slippage = _number(features.get("estimated_slippage_percent"))
    depth_median = _number(features.get("depth_imbalance_median_30s"))
    if depth_median is None:
        depth_median = _number(features.get("depth_imbalance"))
    depth_samples = int(_number(features.get("depth_sample_count_30s")) or 0)
    execution = 0.0
    if spread is not None:
        execution += 3.0 if spread <= 0.05 else 2.0 if spread <= 0.10 else 1.0 if spread <= 0.20 else 0.0
    if slippage is not None:
        execution += 2.0 if slippage <= 0.05 else 1.0 if slippage <= 0.12 else 0.0
    directional_depth = (depth_median or 0.0) * sign
    execution += 3.0 if directional_depth >= 0.20 else 2.0 if directional_depth >= 0 else 1.0 if directional_depth >= -0.20 else 0.0
    execution += 2.0 if depth_samples >= 10 else 1.0 if depth_samples >= 3 else 0.0
    execution = min(10.0, execution)

    components = {
        "structure": round(structure, 2),
        "location_and_room": round(location, 2),
        "confirmation": round(confirmation, 2),
        "participation": round(participation, 2),
        "execution": round(execution, 2),
    }
    score = round(sum(components.values()), 2)
    failures: List[str] = []
    if not directional_events:
        failures.append("NO_DIRECTIONAL_CATALYST")
    if not has_primary_catalyst:
        failures.append("NO_PRIMARY_SETUP_CATALYST")
    if event_types & long_structure_types and event_types & short_structure_types:
        failures.append("CONFLICTING_STRUCTURE_TRANSITIONS")
    if event_types & long_pattern_types and event_types & short_pattern_types:
        failures.append("CONFLICTING_RECENT_PRICE_ACTION")
    if len(event_types) > 6:
        failures.append("EXCESSIVE_SIGNAL_CHURN")
    if confirmation_age is not None and confirmation_age < min_confirmation_seconds:
        failures.append("SETUP_CONFIRMATION_WINDOW_INCOMPLETE")
    if not setup_confirmed:
        failures.append("SETUP_NOT_CONFIRMED_ON_5M")
    if opposite_score >= 4.0 and opposite_score >= event_score * 0.75:
        failures.append("CONFLICTING_DIRECTIONAL_EVIDENCE")
    if entry_drift_atr is not None and entry_drift_atr > max_entry_drift_atr:
        failures.append("ENTRY_EXTENDED_AFTER_SIGNAL")
    if entry_drift_atr is not None and entry_drift_atr < -0.35:
        failures.append("SIGNAL_INVALIDATED_BY_PRICE")
    if structure < 12.0:
        failures.append("WEAK_OR_CONFLICTING_STRUCTURE")
    if room_atr < min_room_atr:
        failures.append("INSUFFICIENT_TARGET_ROOM")
    if confirmation < 8.0:
        failures.append("SETUP_NOT_CONFIRMED")
    if participation < 5.0:
        failures.append("PARTICIPATION_TOO_WEAK")
    if last_trade_age is not None and last_trade_age > max_last_trade_age_seconds:
        failures.append("LAST_TRADE_STALE")
    if score < threshold:
        failures.append("READINESS_SCORE_BELOW_THRESHOLD")
    return {
        "direction": direction,
        "score": score,
        "components": components,
        "failures": failures,
        "diagnostics": {
            "atr_5m": round(atr, 4),
            "ema_5m_fast": round(ema_fast, 4) if ema_fast is not None else None,
            "ema_5m_slow": round(ema_slow, 4) if ema_slow is not None else None,
            "slope_15m_atr": round(slope_15m, 4) if slope_15m is not None else None,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "supportive_level": supportive,
            "opposing_level": opposing,
            "supportive_distance_atr": round(supportive_distance, 4) if supportive_distance is not None else None,
            "target_room_atr": round(room_atr, 4),
            "near_supportive_level": near_supportive,
            "breakout_accepted": breakout_accepted,
            "directional_events": directional_events,
            "has_primary_catalyst": has_primary_catalyst,
            "opposite_directional_events": opposite_events,
            "setup_confirmed_on_5m": setup_confirmed,
            "confirmation_age_seconds": round(confirmation_age, 2) if confirmation_age is not None else None,
            "reference_event_price": reference_event_price,
            "entry_drift_atr": round(entry_drift_atr, 4) if entry_drift_atr is not None else None,
            "relative_volume": rvol,
            "volume_acceleration": acceleration,
            "recent_5m_volume_ratio": round(recent_volume_ratio, 4) if recent_volume_ratio is not None else None,
            "last_trade_age_seconds": last_trade_age,
            "persistent_depth_imbalance": depth_median,
            "depth_sample_count_30s": depth_samples,
        },
    }


def evaluate_trade_readiness(
    *,
    bars: Iterable[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
    features: Dict[str, Any],
    stock: Optional[Dict[str, Any]] = None,
    threshold: float = 75.0,
    direction_margin: float = 10.0,
    min_completed_bars: int = 45,
    min_room_atr: float = 0.55,
    max_last_trade_age_seconds: int = 90,
    min_confirmation_seconds: int = 300,
    max_entry_drift_atr: float = 0.80,
) -> Dict[str, Any]:
    """Score LONG and SHORT independently and return a conservative decision."""
    try:
        evaluated_at = datetime.fromisoformat(str(features.get("received_at")))
    except (TypeError, ValueError):
        evaluated_at = None
    if evaluated_at is not None:
        events = fresh_indicator_events(events, evaluated_at)
    parsed = _parse_bars(bars)
    if len(parsed) < min_completed_bars:
        return {
            "schema_version": READINESS_SCHEMA_VERSION,
            "ready": False,
            "direction": "NEUTRAL",
            "score": 0.0,
            "failures": ["INSUFFICIENT_COMPLETED_BARS"],
            "candidates": {},
            "diagnostics": {"completed_bars": len(parsed)},
        }
    price = _number(features.get("last_price"))
    if price is None or price <= 0:
        return {
            "schema_version": READINESS_SCHEMA_VERSION,
            "ready": False,
            "direction": "NEUTRAL",
            "score": 0.0,
            "failures": ["INVALID_PRICE"],
            "candidates": {},
            "diagnostics": {"completed_bars": len(parsed)},
        }
    bars_5m = [item for item in _aggregate(parsed, 5) if int(item.get("source_bar_count") or 0) >= 5]
    bars_15m = [item for item in _aggregate(parsed, 15) if int(item.get("source_bar_count") or 0) >= 15]
    atr = _atr(bars_5m, 14)
    if atr is None or atr <= 0:
        return {
            "schema_version": READINESS_SCHEMA_VERSION,
            "ready": False,
            "direction": "NEUTRAL",
            "score": 0.0,
            "failures": ["INTRADAY_ATR_UNAVAILABLE"],
            "candidates": {},
            "diagnostics": {"completed_bars": len(parsed), "completed_5m_bars": len(bars_5m)},
        }
    historical = (stock or {}).get("historical") or {}
    levels = _structure_levels(
        bars_5m,
        price=price,
        atr=atr,
        vwap=_number(features.get("vwap")),
        opening_range_high=_number(features.get("opening_range_high")),
        opening_range_low=_number(features.get("opening_range_low")),
        previous_close=_number(historical.get("previous_close")),
    )
    candidates = {
        direction: _candidate(
            direction,
            bars_1m=parsed,
            bars_5m=bars_5m,
            bars_15m=bars_15m,
            events=events,
            features=features,
            levels=levels,
            atr=atr,
            threshold=threshold,
            min_room_atr=min_room_atr,
            max_last_trade_age_seconds=max_last_trade_age_seconds,
            min_confirmation_seconds=min_confirmation_seconds,
            max_entry_drift_atr=max_entry_drift_atr,
        )
        for direction in ("LONG", "SHORT")
    }
    ordered = sorted(candidates.values(), key=lambda item: float(item["score"]), reverse=True)
    selected = ordered[0]
    alternative = ordered[1]
    failures = list(selected["failures"])
    margin = float(selected["score"]) - float(alternative["score"])
    if margin < direction_margin:
        failures.append("DIRECTION_NOT_RESOLVED")
    ready = not failures
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "ready": ready,
        "direction": selected["direction"] if ready else "NEUTRAL",
        "leading_direction": selected["direction"],
        "score": float(selected["score"]),
        "alternative_score": float(alternative["score"]),
        "direction_margin": round(margin, 2),
        "components": selected["components"],
        "failures": failures,
        "candidates": candidates,
        "diagnostics": {
            **selected["diagnostics"],
            "completed_bars": len(parsed),
            "completed_5m_bars": len(bars_5m),
            "completed_15m_bars": len(bars_15m),
            "all_structure_levels": [round(value, 4) for value in levels["levels"]],
        },
    }
