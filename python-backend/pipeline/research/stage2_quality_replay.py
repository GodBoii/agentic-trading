"""Leakage-safe Stage 2 setup-quality feature extraction and replay.

Candidates come from the persisted Intra-Finder shadow events.  Evaluation is
performed at the event time.  Candle and indicator evidence comes from the
last fully completed one-minute candle; live features use observations no
later than the simulated entry.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

IST = "Asia/Kolkata"
FEATURE_SCHEMA_VERSION = 3
EXIT_PROFILES = {
    "balanced_20_20_5m": (0.20, 0.20, 5),
    "quick_15_10_5m": (0.15, 0.10, 5),
    "scalp_20_10_10m": (0.20, 0.10, 10),
    "asymmetric_25_15_10m": (0.25, 0.15, 10),
    "trend_30_15_15m": (0.30, 0.15, 15),
    "trend_40_20_15m": (0.40, 0.20, 15),
}
TAPE_COLUMNS = [
    "received_at",
    "security_id",
    "exchange_segment",
    "symbol",
    "last_price",
    "day_volume",
    "vwap",
    "opening_range_high",
    "opening_range_low",
    "relative_volume",
    "volume_acceleration",
    "estimated_slippage_percent",
    "upper_circuit",
    "lower_circuit",
    "data_fresh",
    "connection_warm",
    "best_bid",
    "best_ask",
    "spread_percent",
    "bid_quantity_5",
    "ask_quantity_5",
    "depth_imbalance",
    "order_count_imbalance",
]


@dataclass(frozen=True)
class QualityPolicy:
    name: str = "quality_v3"
    minimum_score: float = 65.0
    maximum_spread_percent: float = 0.04
    maximum_slippage_percent: float = 0.04
    maximum_break_extension_atr: float = 0.40
    minimum_room_atr: float = 0.0
    maximum_vwap_extension_atr: float = 99.0
    minimum_directional_evidence: int = 0
    cooldown_minutes: int = 45
    entry_cutoff: str = "14:55"
    confirmation_max_gap_seconds: float = 15.0
    target_percent: float = 0.20
    stop_percent: float = 0.20
    horizon_minutes: int = 5
    fixed_round_trip_cost_percent: float = 0.04
    slippage_sides: float = 2.0


def load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            event = json.loads(line)
            evidence = event.get("evidence_timestamps") or []
            if not evidence:
                continue
            event["candidate_time"] = pd.Timestamp(evidence[-1]).tz_convert(IST)
            event["source_line"] = line_number
            events.append(event)
    return events


def load_tape(path: Path) -> pd.DataFrame:
    """Read schema-drifting Parquet fragments without rewriting source data."""
    frames: list[pd.DataFrame] = []
    for parquet_path in sorted(path.rglob("*.parquet")):
        names = set(pq.read_schema(parquet_path).names)
        columns = [column for column in TAPE_COLUMNS if column in names]
        frame = pq.read_table(parquet_path, columns=columns).to_pandas()
        for column in TAPE_COLUMNS:
            if column not in frame:
                frame[column] = np.nan
        frames.append(frame[TAPE_COLUMNS])
    if not frames:
        raise FileNotFoundError(f"No one-second Parquet files found under {path}")
    tape = pd.concat(frames, ignore_index=True, sort=False)
    tape["received_at"] = pd.to_datetime(
        tape["received_at"], format="mixed", utc=True
    ).dt.tz_convert(IST)
    numeric = [column for column in TAPE_COLUMNS if column not in {"received_at", "exchange_segment", "symbol", "data_fresh", "connection_warm"}]
    for column in numeric:
        tape[column] = pd.to_numeric(tape[column], errors="coerce")
    tape = tape.dropna(subset=["received_at", "security_id", "last_price"])
    tape["security_id"] = tape["security_id"].astype(int)
    return tape.sort_values(["security_id", "received_at"]).drop_duplicates(
        ["security_id", "received_at"], keep="last"
    )


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=7).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=7).mean()
    rs = gain / loss.replace(0, np.nan)
    result = 100 - 100 / (1 + rs)
    return result.where(loss > 0, 100.0).where(gain > 0, 0.0)


def build_minute_bars(tape: pd.DataFrame) -> pd.DataFrame:
    indexed = tape.set_index("received_at").sort_index()
    bars = indexed["last_price"].resample("1min").ohlc()
    for column in ["day_volume", "vwap", "opening_range_high", "opening_range_low"]:
        bars[column] = indexed[column].resample("1min").last()
    bars["volume"] = bars["day_volume"].diff().clip(lower=0)
    bars = bars.dropna(subset=["close"])
    bars["ema9"] = bars["close"].ewm(span=9, adjust=False).mean()
    bars["ema21"] = bars["close"].ewm(span=21, adjust=False).mean()
    bars["rsi14"] = _rsi(bars["close"])
    previous_close = bars["close"].shift(1)
    true_range = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - previous_close).abs(),
            (bars["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    bars["atr14"] = true_range.rolling(14, min_periods=7).mean()
    bars["ema9_slope_atr"] = (bars["ema9"] - bars["ema9"].shift(3)) / bars["atr14"].replace(0, np.nan)
    bars["vwap_slope_percent"] = (bars["vwap"] / bars["vwap"].shift(5) - 1) * 100
    bars["trend_move_atr"] = (bars["close"] - bars["close"].shift(5)) / bars["atr14"].replace(0, np.nan)
    travel = bars["close"].diff().abs().rolling(10, min_periods=5).sum()
    bars["trend_efficiency"] = (bars["close"] - bars["close"].shift(10)).abs() / travel.replace(0, np.nan)
    normal_volume = bars["volume"].shift(1).rolling(10, min_periods=5).median()
    bars["minute_volume_ratio"] = bars["volume"] / normal_volume.replace(0, np.nan)
    candle_range = (bars["high"] - bars["low"]).replace(0, np.nan)
    bars["body_ratio"] = (bars["close"] - bars["open"]).abs() / candle_range
    bars["close_location"] = (bars["close"] - bars["low"]) / candle_range
    bars["upper_wick_ratio"] = (bars["high"] - bars[["open", "close"]].max(axis=1)) / candle_range
    bars["lower_wick_ratio"] = (bars[["open", "close"]].min(axis=1) - bars["low"]) / candle_range
    bars["doji"] = bars["body_ratio"] <= 0.12
    previous_open = bars["open"].shift(1)
    previous_close = bars["close"].shift(1)
    bars["bullish_engulfing"] = (
        (bars["close"] > bars["open"])
        & (previous_close < previous_open)
        & (bars["open"] <= previous_close)
        & (bars["close"] >= previous_open)
    )
    bars["bearish_engulfing"] = (
        (bars["close"] < bars["open"])
        & (previous_close > previous_open)
        & (bars["open"] >= previous_close)
        & (bars["close"] <= previous_open)
    )
    return bars


def _nearest_index(times: Any, timestamp: pd.Timestamp, side: str = "left") -> int:
    """Find a timestamp without assuming nanosecond-backed Parquet values.

    Pandas can preserve Arrow timestamps as microseconds.  Converting those to
    integers and comparing them with ``Timestamp.value`` (nanoseconds) silently
    puts every target after the end of the tape.  A DatetimeIndex preserves the
    unit and timezone semantics during ``searchsorted``.
    """
    if isinstance(times, pd.DatetimeIndex):
        return int(times.searchsorted(timestamp, side=side))
    if np.issubdtype(times.dtype, np.datetime64):
        return int(pd.DatetimeIndex(times).searchsorted(timestamp, side=side))
    target = timestamp.value
    if len(times) and np.issubdtype(times.dtype, np.integer):
        magnitude = abs(int(times[len(times) // 2]))
        if magnitude < 100_000_000_000_000_000:
            target //= 1_000
    return int(np.searchsorted(times, target, side=side))


def _path_outcome(
    tape: pd.DataFrame,
    entry_index: int,
    direction_sign: int,
    policy: QualityPolicy,
) -> dict[str, Any]:
    entry_time = tape.iloc[entry_index]["received_at"]
    entry_price = float(tape.iloc[entry_index]["last_price"])
    end_time = entry_time + pd.Timedelta(minutes=policy.horizon_minutes)
    times = pd.DatetimeIndex(tape["received_at"])
    end_index = min(len(tape), _nearest_index(times, end_time, "right"))
    path = tape.iloc[entry_index:end_index]
    if path.empty:
        return {
            "outcome": "NO_DATA",
            "gross_return_percent": np.nan,
            "mfe_percent": np.nan,
            "mae_percent": np.nan,
            "endpoint_return_percent": np.nan,
        }
    returns = direction_sign * (path["last_price"].astype(float) / entry_price - 1) * 100
    target_hits = np.flatnonzero(returns.to_numpy() >= policy.target_percent)
    stop_hits = np.flatnonzero(returns.to_numpy() <= -policy.stop_percent)
    target_index = int(target_hits[0]) if len(target_hits) else None
    stop_index = int(stop_hits[0]) if len(stop_hits) else None
    if target_index is not None and (stop_index is None or target_index < stop_index):
        outcome = "TARGET_FIRST"
        gross = policy.target_percent
    elif stop_index is not None:
        outcome = "STOP_FIRST"
        gross = -policy.stop_percent
    else:
        outcome = "NEITHER"
        gross = float(returns.iloc[-1])
    return {
        "outcome": outcome,
        "gross_return_percent": round(gross, 6),
        "mfe_percent": round(float(returns.max()), 6),
        "mae_percent": round(float(returns.min()), 6),
        "endpoint_return_percent": round(float(returns.iloc[-1]), 6),
    }


def _room_to_structure(
    bars: pd.DataFrame,
    bar_position: int,
    entry_price: float,
    direction_sign: int,
    atr: float,
) -> tuple[float, float | None]:
    previous = bars.iloc[max(0, bar_position - 60) : bar_position]
    if previous.empty or not atr or not math.isfinite(atr):
        return 0.0, None
    buffer = entry_price * 0.0005
    if direction_sign > 0:
        levels = previous.loc[previous["high"] > entry_price + buffer, "high"]
        level = float(levels.min()) if not levels.empty else None
        distance = level - entry_price if level is not None else 2 * atr
    else:
        levels = previous.loc[previous["low"] < entry_price - buffer, "low"]
        level = float(levels.max()) if not levels.empty else None
        distance = entry_price - level if level is not None else 2 * atr
    return max(0.0, distance / atr), level


def _score_features(features: dict[str, Any], direction_sign: int) -> tuple[float, dict[str, float], int]:
    components = {
        "fresh_structure": 0.0,
        "pullback_context": 0.0,
        "candle": 0.0,
        "participation": 0.0,
        "orderflow": 0.0,
        "execution": 0.0,
    }
    if features["confirmation_holds"]:
        components["fresh_structure"] += 10
    extension = features["break_extension_atr"]
    components["fresh_structure"] += (
        12 if extension <= 0.05 else 10 if extension <= 0.10 else 7 if extension <= 0.20 else 3 if extension <= 0.40 else 0
    )
    room = features["room_atr"]
    components["fresh_structure"] += 5 if room >= 1.0 else 3 if room >= 0.5 else 0

    directional_trend = direction_sign * features["trend_move_atr"]
    components["pullback_context"] += (
        12
        if -1.2 <= directional_trend <= -0.3
        else 6
        if -0.3 < directional_trend <= 0.3
        else 3
        if 0.3 < directional_trend <= 1.0
        else 0
    )

    if features["strong_close"]:
        components["candle"] += 5
    if features["directional_candle"]:
        components["candle"] += 3
    if features["directional_engulfing"] or features["directional_rejection"]:
        components["candle"] += 3
    if not features["doji"]:
        components["candle"] += 2

    rvol = features["relative_volume"]
    components["participation"] += 10 if 1.0 <= rvol <= 1.2 else 6 if 0.8 <= rvol <= 1.5 else 2
    acceleration = features["volume_acceleration"]
    components["participation"] += 6 if 1.5 <= acceleration <= 3.0 else 3 if 1.0 <= acceleration <= 4.0 else 0

    depth_mean = direction_sign * features["depth_mean_60s"]
    components["orderflow"] += 5 if 0 <= depth_mean <= 0.3 else 3 if -0.3 < depth_mean < 0 else 0
    persistence = features["depth_direction_persistence_60s"]
    components["orderflow"] += 3 if 0.5 <= persistence <= 0.8 else 1 if persistence > 0.8 else 0

    spread = features["spread_percent"]
    slippage = features["estimated_slippage_percent"]
    components["execution"] += 20 if spread <= 0.02 else 14 if spread <= 0.04 else 8 if spread <= 0.06 else 0
    components["execution"] += 10 if slippage <= 0.01 else 7 if slippage <= 0.02 else 4 if slippage <= 0.04 else 0

    evidence = sum(
        [
            int(features["directional_candle"]),
            int(features["strong_close"]),
            int(features["directional_engulfing"] or features["directional_rejection"]),
            int(-1.2 <= directional_trend <= 0.3),
            int(0 <= depth_mean <= 0.3),
        ]
    )
    return round(sum(components.values()), 2), components, evidence


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _usable_atr(value: Any, price: float) -> float:
    fallback = max(float(price) * 0.001, 0.01)
    atr = _finite(value, fallback)
    return atr if atr > 0 else fallback


def extract_day_features(day_dir: Path, policy: QualityPolicy) -> pd.DataFrame:
    events = load_events(day_dir / "setup-events.jsonl")
    tape = load_tape(day_dir / "one-second")
    profile_policies = {
        name: QualityPolicy(
            **{
                **asdict(policy),
                "target_percent": target,
                "stop_percent": stop,
                "horizon_minutes": horizon,
            }
        )
        for name, (target, stop, horizon) in EXIT_PROFILES.items()
    }
    events_by_security: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        events_by_security.setdefault(int(event["security_id"]), []).append(event)
    results: list[dict[str, Any]] = []
    diagnostics: Counter[str] = Counter()
    tape_security_ids = set(tape["security_id"].unique())
    diagnostics["events_without_tape_security"] = sum(
        len(stock_events)
        for security_id, stock_events in events_by_security.items()
        if security_id not in tape_security_ids
    )
    for group_number, (security_id, stock_tape) in enumerate(tape.groupby("security_id", sort=False), 1):
        stock_events = events_by_security.get(int(security_id))
        if not stock_events:
            continue
        stock_tape = stock_tape.sort_values("received_at").reset_index(drop=True)
        bars = build_minute_bars(stock_tape)
        tape_times = pd.DatetimeIndex(stock_tape["received_at"])
        for event in sorted(stock_events, key=lambda item: item["candidate_time"]):
            candidate_time = event["candidate_time"]
            confirmation_time = candidate_time
            entry_index = _nearest_index(tape_times, confirmation_time, "left")
            if entry_index >= len(stock_tape):
                diagnostics["no_tape_at_confirmation"] += 1
                continue
            entry_row = stock_tape.iloc[entry_index]
            confirmation_gap = (entry_row["received_at"] - confirmation_time).total_seconds()
            bar_label = candidate_time.floor("1min") - pd.Timedelta(minutes=1)
            if bar_label not in bars.index:
                diagnostics["candidate_minute_missing"] += 1
                continue
            bar_position = int(bars.index.get_loc(bar_label))
            bar = bars.iloc[bar_position]
            direction = str(event["direction"])
            sign = 1 if direction == "LONG" else -1
            entry_price = float(entry_row["last_price"])
            atr = _usable_atr(bar["atr14"], entry_price)
            setup = str(event["setup_type"])
            opening_range = event.get("opening_range") or {}
            if setup == "ORB":
                threshold = _finite(opening_range.get("high") if sign > 0 else opening_range.get("low"), entry_price)
                threshold *= 1.0005 if sign > 0 else 0.9995
                confirmation_holds = entry_price >= threshold if sign > 0 else entry_price <= threshold
                break_extension_atr = max(0.0, sign * (entry_price - threshold) / atr)
            else:
                threshold = _finite(entry_row["vwap"], _finite(event.get("vwap"), entry_price))
                confirmation_holds = entry_price > threshold if sign > 0 else entry_price < threshold
                break_extension_atr = abs(entry_price - threshold) / atr
            room_atr, next_structure_level = _room_to_structure(bars, bar_position, entry_price, sign, atr)
            window_start = confirmation_time - pd.Timedelta(seconds=60)
            order_window = stock_tape[
                (stock_tape["received_at"] >= window_start)
                & (stock_tape["received_at"] <= entry_row["received_at"])
            ]
            depth_values = pd.to_numeric(order_window["depth_imbalance"], errors="coerce").dropna()
            depth_mean = float(depth_values.mean()) if not depth_values.empty else 0.0
            depth_persistence = float((sign * depth_values > 0.05).mean()) if not depth_values.empty else 0.0
            close_location = _finite(bar["close_location"], 0.5)
            directional_candle = sign * (_finite(bar["close"]) - _finite(bar["open"])) > 0
            strong_close = close_location >= 0.65 if sign > 0 else close_location <= 0.35
            directional_engulfing = bool(bar["bullish_engulfing"] if sign > 0 else bar["bearish_engulfing"])
            directional_rejection = (
                _finite(bar["lower_wick_ratio"]) >= 0.45 and close_location >= 0.60
                if sign > 0
                else _finite(bar["upper_wick_ratio"]) >= 0.45 and close_location <= 0.40
            )
            spread = _finite(entry_row["spread_percent"], _finite(event.get("spread"), 999))
            slippage = _finite(entry_row["estimated_slippage_percent"], _finite(event.get("estimated_slippage"), 999))
            current_vwap = _finite(entry_row["vwap"], _finite(bar["vwap"], entry_price))
            features = {
                "confirmation_holds": bool(confirmation_holds),
                "room_atr": room_atr,
                "next_structure_level": next_structure_level,
                "break_extension_atr": break_extension_atr,
                "vwap_extension_atr": abs(entry_price - current_vwap) / atr,
                "ema_aligned": sign * (_finite(bar["ema9"]) - _finite(bar["ema21"])) > 0,
                "ema9_slope_atr": _finite(bar["ema9_slope_atr"]),
                "rsi14": _finite(bar["rsi14"], 50.0),
                "vwap_slope_percent": _finite(bar["vwap_slope_percent"]),
                "trend_move_atr": _finite(bar["trend_move_atr"]),
                "trend_efficiency": _finite(bar["trend_efficiency"]),
                "directional_candle": directional_candle,
                "strong_close": strong_close,
                "directional_engulfing": directional_engulfing,
                "directional_rejection": directional_rejection,
                "doji": bool(bar["doji"]),
                "minute_volume_ratio": _finite(bar["minute_volume_ratio"]),
                "relative_volume": _finite(entry_row["relative_volume"], _finite(event.get("relative_volume"))),
                "volume_acceleration": _finite(entry_row["volume_acceleration"], _finite(event.get("volume_acceleration"))),
                "depth_mean_60s": depth_mean,
                "depth_direction_persistence_60s": depth_persistence,
                "depth_observations_60s": len(depth_values),
                "depth_imbalance": _finite(entry_row["depth_imbalance"], _finite((event.get("five_level_depth_summary") or {}).get("imbalance"))),
                "order_count_imbalance": _finite(entry_row["order_count_imbalance"], _finite((event.get("five_level_depth_summary") or {}).get("order_count_imbalance"))),
                "spread_percent": spread,
                "estimated_slippage_percent": slippage,
            }
            quality_score, components, evidence = _score_features(features, sign)
            outcome = _path_outcome(stock_tape, entry_index, sign, policy)
            cost = policy.fixed_round_trip_cost_percent + policy.slippage_sides * slippage
            baseline_index = max(0, _nearest_index(tape_times, candidate_time, "left"))
            if baseline_index >= len(stock_tape):
                baseline_index = len(stock_tape) - 1
            baseline_outcome = _path_outcome(stock_tape, baseline_index, sign, policy)
            result = {
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "market_date": str(event["market_date"]),
                "event_id": str(event["event_id"]),
                "security_id": int(security_id),
                "symbol": str(event.get("symbol") or entry_row["symbol"]),
                "setup_type": setup,
                "direction": direction,
                "candidate_time": candidate_time.isoformat(),
                "confirmation_time": confirmation_time.isoformat(),
                "entry_time": entry_row["received_at"].isoformat(),
                "candidate_price": _finite(event.get("price")),
                "entry_price": entry_price,
                "confirmation_gap_seconds": confirmation_gap,
                "current_setup_score": _finite(event.get("setup_score")),
                "quality_score": quality_score,
                "directional_evidence": evidence,
                "quality_components": json.dumps(components, separators=(",", ":")),
                **features,
                **{f"improved_{key}": value for key, value in outcome.items()},
                "estimated_round_trip_cost_percent": round(cost, 6),
                "improved_net_return_percent": round(_finite(outcome["gross_return_percent"]) - cost, 6),
                **{f"baseline_{key}": value for key, value in baseline_outcome.items()},
                "baseline_net_return_percent": round(_finite(baseline_outcome["gross_return_percent"]) - cost, 6),
            }
            for profile_name, profile_policy in profile_policies.items():
                profile_outcome = _path_outcome(stock_tape, entry_index, sign, profile_policy)
                result.update(
                    {
                        f"{profile_name}_{key}": value
                        for key, value in profile_outcome.items()
                    }
                )
                result[f"{profile_name}_net_return_percent"] = round(
                    _finite(profile_outcome["gross_return_percent"]) - cost,
                    6,
                )
            results.append(result)
            diagnostics["evaluated"] += 1
        if group_number % 100 == 0:
            print(f"Feature extraction: {group_number} stock tapes processed", flush=True)
    print(
        "Feature extraction summary: "
        + ", ".join(f"{key}={value}" for key, value in sorted(diagnostics.items())),
        flush=True,
    )
    if not results:
        raise ValueError(
            f"No Stage 2 events could be evaluated for {day_dir}. "
            f"Diagnostics: {dict(diagnostics)}"
        )
    return pd.DataFrame(results).sort_values(["candidate_time", "security_id"])


def hard_gate_failures(row: pd.Series, policy: QualityPolicy) -> list[str]:
    failures = []
    entry_time = pd.Timestamp(row["entry_time"])
    cutoff_hour, cutoff_minute = map(int, policy.entry_cutoff.split(":"))
    if (entry_time.hour, entry_time.minute) >= (cutoff_hour, cutoff_minute):
        failures.append("ENTRY_CUTOFF")
    if not bool(row["confirmation_holds"]):
        failures.append("CANDLE_CONFIRMATION_FAILED")
    if float(row["confirmation_gap_seconds"]) > policy.confirmation_max_gap_seconds:
        failures.append("CONFIRMATION_DATA_GAP")
    if float(row["spread_percent"]) > policy.maximum_spread_percent:
        failures.append("SPREAD_TOO_WIDE")
    if float(row["estimated_slippage_percent"]) > policy.maximum_slippage_percent:
        failures.append("SCALP_COST_TOO_HIGH")
    if float(row["break_extension_atr"]) > policy.maximum_break_extension_atr:
        failures.append("SETUP_ALREADY_EXTENDED")
    if float(row["room_atr"]) < policy.minimum_room_atr:
        failures.append("INSUFFICIENT_ROOM")
    if float(row["vwap_extension_atr"]) > policy.maximum_vwap_extension_atr:
        failures.append("PRICE_OVEREXTENDED")
    if int(row["directional_evidence"]) < policy.minimum_directional_evidence:
        failures.append("WEAK_DIRECTIONAL_AGREEMENT")
    if float(row["quality_score"]) < policy.minimum_score:
        failures.append("QUALITY_SCORE_BELOW_THRESHOLD")
    return failures


def apply_policy(features: pd.DataFrame, policy: QualityPolicy) -> pd.DataFrame:
    selected_rows = []
    cooldowns: dict[tuple[int, str, str], pd.Timestamp] = {}
    opposing: dict[int, pd.Timestamp] = {}
    for _, row in features.sort_values("entry_time").iterrows():
        failures = hard_gate_failures(row, policy)
        entry_time = pd.Timestamp(row["entry_time"])
        key = (int(row["security_id"]), str(row["setup_type"]), str(row["direction"]))
        previous = cooldowns.get(key)
        if previous is not None and entry_time - previous < pd.Timedelta(minutes=policy.cooldown_minutes):
            failures.append("COOLDOWN")
        previous_stock = opposing.get(int(row["security_id"]))
        if previous_stock is not None and entry_time - previous_stock < pd.Timedelta(minutes=10):
            failures.append("RECENT_STOCK_SIGNAL")
        record = row.to_dict()
        record["gate_failures"] = "|".join(failures)
        record["selected"] = not failures
        selected_rows.append(record)
        if not failures:
            cooldowns[key] = entry_time
            opposing[int(row["security_id"])] = entry_time
    return pd.DataFrame(selected_rows)


def summarize(frame: pd.DataFrame, selected_column: str | None = None, prefix: str = "improved") -> dict[str, Any]:
    data = frame if selected_column is None else frame[frame[selected_column].astype(bool)]
    outcome_column = f"{prefix}_outcome"
    gross_column = f"{prefix}_gross_return_percent"
    net_column = f"{prefix}_net_return_percent"
    outcomes = data[outcome_column].value_counts() if not data.empty else pd.Series(dtype=int)
    resolved = int(outcomes.get("TARGET_FIRST", 0) + outcomes.get("STOP_FIRST", 0))
    return {
        "signals": int(len(data)),
        "unique_stocks": int(data["security_id"].nunique()) if not data.empty else 0,
        "target_first": int(outcomes.get("TARGET_FIRST", 0)),
        "stop_first": int(outcomes.get("STOP_FIRST", 0)),
        "neither": int(outcomes.get("NEITHER", 0)),
        "target_first_percent_all": round(100 * outcomes.get("TARGET_FIRST", 0) / len(data), 2) if len(data) else None,
        "win_percent_when_resolved": round(100 * outcomes.get("TARGET_FIRST", 0) / resolved, 2) if resolved else None,
        "mean_gross_return_percent": round(float(data[gross_column].mean()), 5) if len(data) else None,
        "median_gross_return_percent": round(float(data[gross_column].median()), 5) if len(data) else None,
        "mean_net_return_percent": round(float(data[net_column].mean()), 5) if len(data) else None,
        "median_mfe_percent": round(float(data[f"{prefix}_mfe_percent"].median()), 5) if len(data) else None,
        "median_mae_percent": round(float(data[f"{prefix}_mae_percent"].median()), 5) if len(data) else None,
    }


def policy_dict(policy: QualityPolicy) -> dict[str, Any]:
    return asdict(policy)
