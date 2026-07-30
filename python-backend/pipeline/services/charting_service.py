from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CandlestickChartService:
    """Generates professional candlestick chart images optimized for LLM vision analysis.

    Produces five neutral price charts and four dedicated evidence charts.
    Every chart is derived from OHLCV; order-flow data is never synthesized.
    """

    CURRENT_DAY_TIMEFRAMES: List[int] = [1, 5, 15]
    PREVIOUS_DAY_TIMEFRAMES: List[int] = [5, 15]

    # Color palette — carefully chosen for LLM visual clarity
    COLORS = {
        "bg": "#0d1117",
        "panel_bg": "#0d1117",
        "candle_up": "#00dc82",
        "candle_up_edge": "#00a862",
        "candle_down": "#ff4757",
        "candle_down_edge": "#cc2f3f",
        "wick_up": "#00dc82",
        "wick_down": "#ff4757",
        "vwap": "#ff9f1a",
        "ema9": "#00bfff",
        "ema21": "#e040fb",
        "bb_fill": "#4a90d9",
        "bb_line": "#4a90d9",
        "rsi_line": "#f5c842",
        "rsi_ob": "#ff4757",
        "rsi_os": "#00dc82",
        "rsi_mid": "#4a4a4a",
        "cvd_pos": "#3b82f6",
        "cvd_neg": "#ff4757",
        "sr_support": "#00dc82",
        "sr_resistance": "#ff4757",
        "sd_demand": "#00dc82",
        "sd_supply": "#ff4757",
        "prev_high": "#fbbf24",
        "prev_low": "#a78bfa",
        "prev_close": "#94a3b8",
        "grid": "#1e2a3a",
        "text": "#e2e8f0",
        "text_dim": "#94a3b8",
        "spine": "#2d3748",
        "pattern_bull": "#00dc82",
        "pattern_bear": "#ff4757",
    }

    def __init__(self, market_timezone: str, market_open: Tuple[int, int] = (9, 15), market_close: Tuple[int, int] = (15, 30)):
        self.market_timezone = market_timezone
        self.resolved_timezone = self._resolve_timezone(market_timezone)
        self.market_open = market_open
        self.market_close = market_close

    def build_intraday_chart_set(
        self,
        frame: pd.DataFrame,
        display_name: str,
        market_date: str,
        output_dir: Path,
    ) -> Dict[str, Any]:
        """Build the full chart set with technical metadata for LLM consumption."""
        output_dir.mkdir(parents=True, exist_ok=True)
        local_frame = self._to_market_frame(frame)

        today_frame = self._day_frame(local_frame, market_date)
        if today_frame.empty:
            raise ValueError("No intraday candles available for the requested market date.")
        data_as_of = today_frame.index[-1]

        # Get previous day frame for S/R computation
        market_day = date.fromisoformat(market_date)
        available_previous_dates = sorted(
            {
                timestamp.date()
                for timestamp in local_frame["timestamp"]
                if timestamp.date() < market_day
            }
        )
        prev_date = (
            available_previous_dates[-1]
            if available_previous_dates
            else self._previous_trading_day(market_date)
        )
        prev_date_str = prev_date.isoformat()
        prev_frame = self._day_frame(local_frame, prev_date_str)

        # Compute previous day levels for current day charts
        prev_day_levels = self._compute_prev_day_levels(prev_frame) if not prev_frame.empty else {}

        charts: Dict[str, Any] = {}
        chart_paths_ordered: List[str] = []
        technical_metadata: Dict[str, Any] = {}

        for timeframe in self.CURRENT_DAY_TIMEFRAMES:
            resampled = self._resample_frame(today_frame, timeframe)
            tf_label = self._timeframe_label(timeframe)
            filename = f"{self._slugify(display_name)}-{market_date}-current-{tf_label}.png"
            path = output_dir / filename

            # Compute all indicators and zones
            enriched = self._compute_full_indicators(resampled)
            sr_levels = self._detect_support_resistance(enriched, prev_day_levels)
            sd_zones = self._detect_supply_demand_zones(enriched)
            patterns = self._detect_candlestick_patterns(enriched)

            self._render_chart(
                frame=enriched,
                title=f"{display_name} {tf_label}",
                subtitle=(
                    f"CURRENT DAY \u2014 {market_date} | "
                    f"DATA THROUGH {data_as_of.strftime('%H:%M:%S IST')}"
                ),
                output_path=path,
                market_date=market_date,
                timeframe_minutes=timeframe,
                sr_levels=sr_levels,
                sd_zones=sd_zones,
                patterns=patterns,
                prev_day_levels=prev_day_levels,
            )
            key = f"current_{tf_label}"
            charts[key] = {
                "timeframe_minutes": timeframe,
                "label": tf_label,
                "day_type": "current",
                "chart_type": "price",
                "date": market_date,
                "path": str(path),
                "candles": int(len(resampled)),
                "data_as_of_ist": data_as_of.isoformat(),
                "last_candle_start_ist": resampled.index[-1].isoformat(),
                "last_candle_complete": bool(
                    datetime.now(self.resolved_timezone)
                    >= resampled.index[-1].to_pydatetime() + timedelta(minutes=timeframe)
                ),
            }
            chart_paths_ordered.append(str(path))

            # Store metadata for the primary analysis timeframe (5m)
            if timeframe == 5:
                technical_metadata = self._build_technical_metadata(
                    enriched, sr_levels, sd_zones, patterns, prev_day_levels
                )
                technical_metadata.update(
                    {
                        "data_as_of_ist": data_as_of.isoformat(),
                        "last_candle_start_ist": resampled.index[-1].isoformat(),
                        "last_candle_complete": charts[key]["last_candle_complete"],
                    }
                )

        # Previous day charts
        if not prev_frame.empty:
            for timeframe in self.PREVIOUS_DAY_TIMEFRAMES:
                resampled = self._resample_frame(prev_frame, timeframe)
                tf_label = self._timeframe_label(timeframe)
                filename = f"{self._slugify(display_name)}-{prev_date_str}-previous-{tf_label}.png"
                path = output_dir / filename

                enriched = self._compute_full_indicators(resampled)
                sr_levels_prev = self._detect_support_resistance(enriched, {})
                sd_zones_prev = self._detect_supply_demand_zones(enriched)
                patterns_prev = self._detect_candlestick_patterns(enriched)

                self._render_chart(
                    frame=enriched,
                    title=f"{display_name} {tf_label}",
                    subtitle=f"PREVIOUS DAY \u2014 {prev_date_str}",
                    output_path=path,
                    market_date=prev_date_str,
                    timeframe_minutes=timeframe,
                    sr_levels=sr_levels_prev,
                    sd_zones=sd_zones_prev,
                    patterns=patterns_prev,
                    prev_day_levels={},
                )
                key = f"previous_{tf_label}"
                charts[key] = {
                    "timeframe_minutes": timeframe,
                    "label": tf_label,
                    "day_type": "previous",
                    "chart_type": "price",
                    "date": prev_date_str,
                    "path": str(path),
                    "candles": int(len(resampled)),
                }
                chart_paths_ordered.append(str(path))

        analytical_specs = [
            (
                "volume_participation",
                f"{self._slugify(display_name)}-{market_date}-volume-participation.png",
                self._render_volume_participation_chart,
            ),
            (
                "momentum_volatility",
                f"{self._slugify(display_name)}-{market_date}-momentum-volatility.png",
                self._render_momentum_volatility_chart,
            ),
            (
                "price_structure_liquidity",
                f"{self._slugify(display_name)}-{market_date}-price-structure-liquidity.png",
                self._render_price_structure_liquidity_chart,
            ),
            (
                "tpo_profile",
                f"{self._slugify(display_name)}-{market_date}-tpo-profile.png",
                self._render_tpo_profile_chart,
            ),
        ]
        for key, filename, renderer in analytical_specs:
            path = output_dir / filename
            metadata = renderer(
                local_frame=local_frame,
                today_frame=today_frame,
                previous_frame=prev_frame,
                display_name=display_name,
                market_date=market_date,
                previous_market_date=prev_date_str,
                data_as_of=data_as_of,
                output_path=path,
                prev_day_levels=prev_day_levels,
            )
            charts[key] = {
                "chart_type": key,
                "day_type": "analytical",
                "date": market_date,
                "path": str(path),
                "data_as_of_ist": data_as_of.isoformat(),
                "metadata": metadata,
            }
            chart_paths_ordered.append(str(path))

        return {
            "market_date": market_date,
            "data_as_of_ist": data_as_of.isoformat(),
            "charts_built_at_ist": datetime.now(self.resolved_timezone).isoformat(),
            "previous_market_date": prev_date_str if not prev_frame.empty else None,
            "chart_count": len(charts),
            "charts": charts,
            "chart_paths_ordered": chart_paths_ordered,
            "chart_contract_version": "stock-evidence-v4",
            "technical_metadata": technical_metadata,
        }

    # ─── INDICATOR COMPUTATION ─────────────────────────────────────────────

    def _compute_full_indicators(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Compute all technical indicators on a resampled OHLCV frame."""
        if frame.empty:
            return frame
        df = frame.copy()

        # EMA 9 and 21
        df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()

        # Bollinger Bands (20, 2)
        df["bb_mid"] = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_mid"] + 2 * bb_std
        df["bb_lower"] = df["bb_mid"] - 2 * bb_std

        # RSI (14)
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        return df

    def _compute_prev_day_levels(self, prev_frame: pd.DataFrame) -> Dict[str, float]:
        """Extract previous day high, low, close for current day context."""
        if prev_frame.empty:
            return {}
        return {
            "prev_high": float(prev_frame["high"].max()),
            "prev_low": float(prev_frame["low"].min()),
            "prev_close": float(prev_frame["close"].iloc[-1]),
        }

    # ─── SUPPORT & RESISTANCE DETECTION ────────────────────────────────────

    def _detect_support_resistance(
        self, frame: pd.DataFrame, prev_day_levels: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Detect S/R levels using pivot points + previous day levels."""
        levels: List[Dict[str, Any]] = []
        if frame.empty or len(frame) < 5:
            return levels

        highs = frame["high"].values
        lows = frame["low"].values
        lookback = 3

        # Pivot highs (resistance)
        for i in range(lookback, len(highs) - lookback):
            if all(highs[i] >= highs[i - j] for j in range(1, lookback + 1)) and \
               all(highs[i] >= highs[i + j] for j in range(1, lookback + 1)):
                levels.append({"price": float(highs[i]), "type": "resistance", "source": "pivot"})

        # Pivot lows (support)
        for i in range(lookback, len(lows) - lookback):
            if all(lows[i] <= lows[i - j] for j in range(1, lookback + 1)) and \
               all(lows[i] <= lows[i + j] for j in range(1, lookback + 1)):
                levels.append({"price": float(lows[i]), "type": "support", "source": "pivot"})

        # Add previous day levels
        if prev_day_levels:
            last_close = float(frame["close"].iloc[-1])
            ph = prev_day_levels.get("prev_high")
            pl = prev_day_levels.get("prev_low")
            pc = prev_day_levels.get("prev_close")
            if ph:
                levels.append({"price": ph, "type": "resistance" if last_close < ph else "support", "source": "prev_high"})
            if pl:
                levels.append({"price": pl, "type": "support" if last_close > pl else "resistance", "source": "prev_low"})
            if pc:
                levels.append({"price": pc, "type": "resistance" if last_close < pc else "support", "source": "prev_close"})

        # Deduplicate levels that are within 0.3% of each other
        levels.sort(key=lambda x: x["price"])
        deduplicated: List[Dict[str, Any]] = []
        for level in levels:
            if not deduplicated or abs(level["price"] - deduplicated[-1]["price"]) / deduplicated[-1]["price"] > 0.003:
                deduplicated.append(level)
        return deduplicated

    # ─── SUPPLY & DEMAND ZONE DETECTION ────────────────────────────────────

    def _detect_supply_demand_zones(self, frame: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect supply/demand zones using impulse + base method."""
        zones: List[Dict[str, Any]] = []
        if frame.empty or len(frame) < 5:
            return zones

        closes = frame["close"].values
        opens = frame["open"].values
        highs = frame["high"].values
        lows = frame["low"].values
        atr_values = frame["atr"].values if "atr" in frame.columns else None

        if atr_values is None:
            return zones

        for i in range(2, len(frame)):
            body_size = abs(closes[i] - opens[i])
            atr_val = atr_values[i] if not np.isnan(atr_values[i]) else 0

            # Impulse candle: body > 1.8x ATR
            if atr_val > 0 and body_size > 1.8 * atr_val:
                is_bullish_impulse = closes[i] > opens[i]

                # Find the base (1-3 candles before the impulse)
                base_start = max(0, i - 3)
                base_end = i

                if is_bullish_impulse:
                    # Demand zone: base before a big green candle
                    zone_low = float(min(lows[base_start:base_end]))
                    zone_high = float(max(highs[base_start:base_end]))
                    # Check if zone is below current price (still valid demand)
                    if closes[-1] > zone_high:
                        zones.append({
                            "type": "demand",
                            "zone_high": zone_high,
                            "zone_low": zone_low,
                            "strength": "strong" if body_size > 2.5 * atr_val else "moderate",
                            "candle_index": i,
                        })
                else:
                    # Supply zone: base before a big red candle
                    zone_low = float(min(lows[base_start:base_end]))
                    zone_high = float(max(highs[base_start:base_end]))
                    # Check if zone is above current price (still valid supply)
                    if closes[-1] < zone_low:
                        zones.append({
                            "type": "supply",
                            "zone_high": zone_high,
                            "zone_low": zone_low,
                            "strength": "strong" if body_size > 2.5 * atr_val else "moderate",
                            "candle_index": i,
                        })

        # Keep only the most recent/strongest zones (max 3 of each type)
        demand_zones = sorted([z for z in zones if z["type"] == "demand"], key=lambda x: x["candle_index"], reverse=True)[:3]
        supply_zones = sorted([z for z in zones if z["type"] == "supply"], key=lambda x: x["candle_index"], reverse=True)[:3]
        return demand_zones + supply_zones

    # ─── CANDLESTICK PATTERN DETECTION ─────────────────────────────────────

    def _detect_candlestick_patterns(self, frame: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect key candlestick patterns for annotation."""
        patterns: List[Dict[str, Any]] = []
        if frame.empty or len(frame) < 3:
            return patterns

        opens = frame["open"].values
        closes = frame["close"].values
        highs = frame["high"].values
        lows = frame["low"].values
        atr_values = frame["atr"].values if "atr" in frame.columns else np.full(len(frame), 1.0)

        for i in range(1, len(frame)):
            body = abs(closes[i] - opens[i])
            candle_range = highs[i] - lows[i]
            atr = atr_values[i] if not np.isnan(atr_values[i]) else 1.0

            if candle_range == 0:
                continue

            body_ratio = body / candle_range
            upper_shadow = highs[i] - max(opens[i], closes[i])
            lower_shadow = min(opens[i], closes[i]) - lows[i]

            # Doji: very small body relative to range
            if body_ratio < 0.1 and candle_range > 0.3 * atr:
                patterns.append({"index": i, "pattern": "Doji", "bias": "neutral", "price": float(closes[i])})
                continue

            # Hammer: small body at top, long lower shadow (>2x body)
            if lower_shadow > 2 * body and upper_shadow < body * 0.5 and closes[i] > opens[i]:
                patterns.append({"index": i, "pattern": "Hammer", "bias": "bullish", "price": float(lows[i])})
                continue

            # Shooting Star: small body at bottom, long upper shadow
            if upper_shadow > 2 * body and lower_shadow < body * 0.5 and closes[i] < opens[i]:
                patterns.append({"index": i, "pattern": "Shooting Star", "bias": "bearish", "price": float(highs[i])})
                continue

            # Bullish Engulfing
            if i >= 1 and closes[i - 1] < opens[i - 1] and closes[i] > opens[i]:
                prev_body = abs(closes[i - 1] - opens[i - 1])
                if body > prev_body * 1.2 and opens[i] <= closes[i - 1] and closes[i] >= opens[i - 1]:
                    patterns.append({"index": i, "pattern": "Bull Engulf", "bias": "bullish", "price": float(closes[i])})
                    continue

            # Bearish Engulfing
            if i >= 1 and closes[i - 1] > opens[i - 1] and closes[i] < opens[i]:
                prev_body = abs(closes[i - 1] - opens[i - 1])
                if body > prev_body * 1.2 and opens[i] >= closes[i - 1] and closes[i] <= opens[i - 1]:
                    patterns.append({"index": i, "pattern": "Bear Engulf", "bias": "bearish", "price": float(closes[i])})
                    continue

        # Dedupe: drop consecutive same-type patterns within 2 candles of each other
        deduped: List[Dict[str, Any]] = []
        for p in patterns:
            if deduped and deduped[-1]["pattern"] == p["pattern"] and (p["index"] - deduped[-1]["index"]) <= 2:
                continue
            deduped.append(p)
        # Only keep the last 5 most recent patterns to avoid clutter
        return deduped[-5:]

    # ─── TECHNICAL METADATA FOR LLM TEXT PROMPT ────────────────────────────

    def _build_technical_metadata(
        self,
        frame: pd.DataFrame,
        sr_levels: List[Dict[str, Any]],
        sd_zones: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        prev_day_levels: Dict[str, float],
    ) -> Dict[str, Any]:
        """Build a concise metadata dict to send alongside chart images to LLM."""
        if frame.empty:
            return {}

        last = frame.iloc[-1]
        meta: Dict[str, Any] = {}

        # Current indicator readings
        meta["latest_price"] = round(float(last["close"]), 2)
        meta["vwap"] = round(float(last["vwap"]), 2) if "vwap" in frame.columns and not pd.isna(last.get("vwap")) else None
        meta["ema9"] = round(float(last["ema9"]), 2) if "ema9" in frame.columns and not pd.isna(last.get("ema9")) else None
        meta["ema21"] = round(float(last["ema21"]), 2) if "ema21" in frame.columns and not pd.isna(last.get("ema21")) else None
        meta["rsi"] = round(float(last["rsi"]), 1) if "rsi" in frame.columns and not pd.isna(last.get("rsi")) else None
        meta["bb_upper"] = round(float(last["bb_upper"]), 2) if "bb_upper" in frame.columns and not pd.isna(last.get("bb_upper")) else None
        meta["bb_lower"] = round(float(last["bb_lower"]), 2) if "bb_lower" in frame.columns and not pd.isna(last.get("bb_lower")) else None
        meta["atr"] = round(float(last["atr"]), 2) if "atr" in frame.columns and not pd.isna(last.get("atr")) else None
        # EMA crossover state
        if meta["ema9"] and meta["ema21"]:
            meta["ema_state"] = "bullish_cross" if meta["ema9"] > meta["ema21"] else "bearish_cross"

        # Price position relative to key levels
        if meta["vwap"]:
            meta["price_vs_vwap"] = "above" if meta["latest_price"] > meta["vwap"] else "below"

        # S/R levels (concise)
        supports = [l for l in sr_levels if l["type"] == "support"]
        resistances = [l for l in sr_levels if l["type"] == "resistance"]
        meta["support_levels"] = [round(l["price"], 2) for l in supports[:3]]
        meta["resistance_levels"] = [round(l["price"], 2) for l in resistances[:3]]

        # S/D zones (concise)
        meta["demand_zones"] = [{"high": round(z["zone_high"], 2), "low": round(z["zone_low"], 2), "strength": z["strength"]} for z in sd_zones if z["type"] == "demand"][:2]
        meta["supply_zones"] = [{"high": round(z["zone_high"], 2), "low": round(z["zone_low"], 2), "strength": z["strength"]} for z in sd_zones if z["type"] == "supply"][:2]

        # Previous day levels
        if prev_day_levels:
            meta["prev_day"] = {k: round(v, 2) for k, v in prev_day_levels.items()}

        # Detected patterns
        meta["patterns_detected"] = [{"pattern": p["pattern"], "bias": p["bias"], "at_price": round(p["price"], 2)} for p in patterns]

        return meta

    # ─── RESAMPLING WITH BASE INDICATORS ───────────────────────────────────

    def _resample_frame(self, frame: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
        rule = f"{timeframe_minutes}min"

        df = self._add_base_indicators(frame)

        ohlcv = (
            df[["open", "high", "low", "close", "volume", "vwap"]]
            .resample(rule, label="left", closed="left")
            .agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "vwap": "last",
            })
            .dropna(subset=["open", "high", "low", "close"])
        )

        # ATR (14) — use min_periods=2 so we get a value even with limited data
        high_low = ohlcv["high"] - ohlcv["low"]
        high_close_prev = (ohlcv["high"] - ohlcv["close"].shift(1)).abs()
        low_close_prev = (ohlcv["low"] - ohlcv["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        ohlcv["atr"] = true_range.rolling(window=14, min_periods=2).mean()
        ohlcv["atr"] = ohlcv["atr"].bfill()
        # Final fallback: if still NaN (only 1 candle), use that candle's range
        ohlcv["atr"] = ohlcv["atr"].fillna(high_low)

        return ohlcv

    def _add_base_indicators(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        df = frame.copy()

        # VWAP
        df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3.0
        df["vp"] = df["typical_price"] * df["volume"]
        df["cum_vp"] = df["vp"].cumsum()
        df["cum_vol"] = df["volume"].cumsum()
        df["vwap"] = df["cum_vp"] / df["cum_vol"]

        return df

    # ─── CHART RENDERING ───────────────────────────────────────────────────

    def _render_chart(
        self,
        frame: pd.DataFrame,
        title: str,
        subtitle: str,
        output_path: Path,
        market_date: str,
        timeframe_minutes: int,
        sr_levels: List[Dict[str, Any]],
        sd_zones: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        prev_day_levels: Dict[str, float],
    ) -> None:
        """Render one uncluttered price chart for a specific decision role.

        Oscillators, volume statistics, and candlestick detections are deliberately
        kept in the JSON metadata. The image is reserved for price geometry.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        from matplotlib.ticker import FuncFormatter

        if frame.empty:
            raise ValueError(f"Cannot render empty chart for {title}.")

        colors = self.COLORS
        visible_bars = {1: 90, 5: 90, 15: 64}.get(timeframe_minutes, 80)
        plot_frame = frame.iloc[-visible_bars:].copy()
        if plot_frame.index.tz is not None:
            plot_frame.index = plot_frame.index.tz_localize(None)

        candle_count = len(plot_frame)
        x_positions = np.arange(candle_count, dtype=float)
        timestamps = plot_frame.index.to_pydatetime()
        candle_width = 0.72 if candle_count > 60 else 0.64
        x_right = candle_count - 1 + 4.5

        candle_low = float(plot_frame["low"].min())
        candle_high = float(plot_frame["high"].max())
        visible_span = max(candle_high - candle_low, 0.01)
        latest_atr = self._latest_finite(plot_frame, "atr")
        y_padding = max(visible_span * 0.06, latest_atr * 0.35, 0.02)
        y_min = candle_low - y_padding
        y_max = candle_high + y_padding

        latest_close = float(plot_frame["close"].iloc[-1])
        selected_levels = sorted(
            (
                level for level in sr_levels
                if y_min <= float(level.get("price", math.nan)) <= y_max
            ),
            key=lambda level: abs(float(level["price"]) - latest_close),
        )[:4]
        selected_zones: List[Dict[str, Any]] = []
        for zone_type in ("demand", "supply"):
            candidates = [
                zone for zone in sd_zones
                if zone.get("type") == zone_type
                and float(zone.get("zone_high", -math.inf)) >= y_min
                and float(zone.get("zone_low", math.inf)) <= y_max
            ]
            if candidates:
                selected_zones.append(
                    min(
                        candidates,
                        key=lambda zone: abs(
                            (float(zone["zone_low"]) + float(zone["zone_high"])) / 2
                            - latest_close
                        ),
                    )
                )

        fig, ax_price = plt.subplots(figsize=(16, 9))
        fig.patch.set_facecolor(colors["bg"])
        ax_price.set_facecolor(colors["panel_bg"])

        for zone in selected_zones:
            zone_low = max(float(zone["zone_low"]), y_min)
            zone_high = min(float(zone["zone_high"]), y_max)
            zone_color = (
                colors["sd_demand"]
                if zone["type"] == "demand"
                else colors["sd_supply"]
            )
            zone_alpha = 0.13 if zone.get("strength") == "strong" else 0.08
            ax_price.axhspan(
                zone_low,
                zone_high,
                color=zone_color,
                alpha=zone_alpha,
                zorder=0,
            )
            ax_price.text(
                x_right - 0.25,
                (zone_low + zone_high) / 2,
                f"{zone['type'].upper()} ZONE",
                color=zone_color,
                fontsize=8,
                fontweight="bold",
                ha="right",
                va="center",
                zorder=7,
            )

        for level in selected_levels:
            level_price = float(level["price"])
            level_color = (
                colors["sr_support"]
                if level["type"] == "support"
                else colors["sr_resistance"]
            )
            ax_price.axhline(
                level_price,
                color=level_color,
                linestyle="--",
                linewidth=0.8,
                alpha=0.38,
                zorder=1,
            )

        previous_level_specs = (
            ("prev_high", "PDH", colors["prev_high"]),
            ("prev_low", "PDL", colors["prev_low"]),
            ("prev_close", "PDC", colors["prev_close"]),
        )
        offscreen_top: List[str] = []
        offscreen_bottom: List[str] = []
        for key, label, level_color in previous_level_specs:
            value = prev_day_levels.get(key)
            if value is None or not math.isfinite(float(value)):
                continue
            price = float(value)
            if y_min <= price <= y_max:
                ax_price.axhline(
                    price,
                    color=level_color,
                    linestyle=":",
                    linewidth=1.0,
                    alpha=0.78,
                    zorder=1,
                )
                ax_price.text(
                    x_right - 0.25,
                    price,
                    f"{label} {price:.2f}",
                    fontsize=8,
                    color=level_color,
                    ha="right",
                    va="bottom",
                    fontweight="bold",
                    zorder=7,
                )
            elif price > y_max:
                offscreen_top.append(f"↑ {label} {price:.2f}")
            else:
                offscreen_bottom.append(f"↓ {label} {price:.2f}")

        for column, color, label, width in (
            ("ema9", colors["ema9"], "EMA 9", 1.25),
            ("ema21", colors["ema21"], "EMA 21", 1.25),
            ("vwap", colors["vwap"], "VWAP", 1.7),
        ):
            if column in plot_frame.columns and not plot_frame[column].isna().all():
                ax_price.plot(
                    x_positions,
                    plot_frame[column].to_numpy(dtype=float),
                    color=color,
                    linewidth=width,
                    alpha=0.88,
                    label=label,
                    zorder=3,
                )

        for idx in range(candle_count):
            row = plot_frame.iloc[idx]
            x_value = x_positions[idx]
            open_price = float(row["open"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            close_price = float(row["close"])
            is_up = close_price >= open_price
            face_color = colors["candle_up"] if is_up else colors["candle_down"]
            edge_color = (
                colors["candle_up_edge"] if is_up else colors["candle_down_edge"]
            )
            wick_color = colors["wick_up"] if is_up else colors["wick_down"]

            ax_price.vlines(
                x_value,
                low_price,
                high_price,
                color=wick_color,
                linewidth=1.45,
                zorder=5,
            )
            body_low = min(open_price, close_price)
            body_height = max(
                abs(close_price - open_price),
                visible_span * 0.0018,
            )
            ax_price.add_patch(
                Rectangle(
                    (x_value - candle_width / 2, body_low),
                    candle_width,
                    body_height,
                    facecolor=face_color,
                    edgecolor=edge_color,
                    linewidth=0.85,
                    zorder=6,
                )
            )

        ax_price.axhline(
            latest_close,
            color=colors["text"],
            linewidth=0.75,
            alpha=0.30,
            zorder=2,
        )
        ax_price.text(
            x_right - 0.15,
            latest_close,
            f"LAST {latest_close:.2f}",
            color=colors["text"],
            fontsize=8,
            fontweight="bold",
            ha="right",
            va="bottom",
            bbox={
                "boxstyle": "round,pad=0.2",
                "facecolor": colors["bg"],
                "edgecolor": colors["spine"],
                "alpha": 0.92,
            },
            zorder=8,
        )

        index_to_time = {idx: timestamps[idx] for idx in range(candle_count)}

        def format_time(x_value: float, _position: int) -> str:
            index = int(round(x_value))
            if 0 <= index < candle_count:
                return index_to_time[index].strftime("%H:%M")
            return ""

        tick_step = max(1, candle_count // 10)
        ax_price.set_xticks(np.arange(0, candle_count, tick_step))
        ax_price.xaxis.set_major_formatter(FuncFormatter(format_time))
        ax_price.set_xlim(-0.9, x_right)
        ax_price.set_ylim(y_min, y_max)

        latest_vwap = self._latest_finite(plot_frame, "vwap")
        latest_atr = self._latest_finite(plot_frame, "atr")
        market_day = date.fromisoformat(market_date)
        last_start = pd.Timestamp(timestamps[-1]).to_pydatetime().replace(
            tzinfo=self.resolved_timezone
        )
        is_complete = (
            datetime.now(self.resolved_timezone)
            >= last_start + timedelta(minutes=timeframe_minutes)
        ) or market_day < datetime.now(self.resolved_timezone).date()
        partial_marker = "" if is_complete else " | PARTIAL LAST CANDLE"
        ax_price.set_title(
            (
                f"{title} | LAST ₹{latest_close:.2f} | "
                f"VWAP ₹{latest_vwap:.2f} | ATR(14) ₹{latest_atr:.2f}"
                f"{partial_marker}"
            ),
            color=colors["text"],
            fontsize=14,
            pad=14,
            fontweight="bold",
        )
        fig.suptitle(
            subtitle,
            color="#82aaff",
            fontsize=11,
            fontweight="bold",
            y=0.985,
        )

        if offscreen_top:
            ax_price.text(
                0.99,
                0.985,
                "  |  ".join(offscreen_top),
                transform=ax_price.transAxes,
                color=colors["text_dim"],
                fontsize=8,
                ha="right",
                va="top",
            )
        if offscreen_bottom:
            ax_price.text(
                0.99,
                0.015,
                "  |  ".join(offscreen_bottom),
                transform=ax_price.transAxes,
                color=colors["text_dim"],
                fontsize=8,
                ha="right",
                va="bottom",
            )

        ax_price.legend(
            loc="upper left",
            ncol=3,
            facecolor=colors["bg"],
            edgecolor=colors["spine"],
            labelcolor=colors["text"],
            fontsize=9,
            framealpha=0.92,
        )
        ax_price.grid(
            color=colors["grid"],
            linestyle="--",
            linewidth=0.5,
            alpha=0.45,
        )
        ax_price.tick_params(colors=colors["text_dim"], labelsize=9)
        for spine in ax_price.spines.values():
            spine.set_color(colors["spine"])
        ax_price.set_ylabel("Price (₹)", color=colors["text_dim"], fontsize=10)
        ax_price.set_xlabel("Time (IST)", color=colors["text_dim"], fontsize=10)
        plt.setp(ax_price.get_xticklabels(), rotation=35, ha="right")
        plt.subplots_adjust(left=0.07, right=0.985, top=0.91, bottom=0.11)
        fig.savefig(
            output_path,
            dpi=180,
            bbox_inches="tight",
            facecolor=colors["bg"],
        )
        plt.close(fig)

    def _render_volume_participation_chart(
        self,
        *,
        local_frame: pd.DataFrame,
        today_frame: pd.DataFrame,
        display_name: str,
        market_date: str,
        data_as_of: pd.Timestamp,
        output_path: Path,
        **_: Any,
    ) -> Dict[str, Any]:
        """Render volume evidence without pretending candle color is trade side."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        five = self._resample_frame(today_frame, 5)
        if five.empty:
            raise ValueError("No current-session volume data.")

        current_day = date.fromisoformat(market_date)
        session_curves: List[pd.DataFrame] = []
        for session_date, session in local_frame.groupby(local_frame["timestamp"].dt.date, sort=True):
            session = session.copy()
            first_minute = session["timestamp"].min()
            last_minute = session["timestamp"].max()
            if session_date < current_day and (
                first_minute.hour * 60 + first_minute.minute > 9 * 60 + 20
                or last_minute.hour * 60 + last_minute.minute < 15 * 60 + 25
            ):
                continue
            session_start = pd.Timestamp(
                datetime(
                    session_date.year,
                    session_date.month,
                    session_date.day,
                    self.market_open[0],
                    self.market_open[1],
                    tzinfo=self.resolved_timezone,
                )
            )
            session_end = pd.Timestamp(
                datetime(
                    session_date.year,
                    session_date.month,
                    session_date.day,
                    self.market_close[0],
                    self.market_close[1],
                    tzinfo=self.resolved_timezone,
                )
            ) - pd.Timedelta(minutes=1)
            if session_date == current_day:
                session_end = min(session_end, last_minute.floor("min"))
            minute_index = pd.date_range(session_start, session_end, freq="1min")
            minute_volume = (
                session.set_index("timestamp")["volume"]
                .groupby(level=0)
                .sum()
                .reindex(minute_index, fill_value=0.0)
            )
            curve = pd.DataFrame(
                {
                    "timestamp": minute_index,
                    "market_date": session_date,
                    "minute_of_day": minute_index.hour * 60 + minute_index.minute,
                    "volume": minute_volume.to_numpy(dtype=float),
                }
            )
            curve["cumulative_volume"] = curve["volume"].cumsum()
            session_curves.append(curve)
        history = pd.concat(session_curves, ignore_index=True) if session_curves else pd.DataFrame()
        prior = history.loc[history["market_date"] < current_day]
        completed_dates = sorted(prior["market_date"].unique())[-15:]
        prior = prior.loc[prior["market_date"].isin(completed_dates)]
        expected_by_minute = (
            prior.groupby("minute_of_day")["cumulative_volume"].median()
            if not prior.empty
            else pd.Series(dtype=float)
        )

        current = history.loc[history["market_date"] == current_day].copy()
        current_expected = current["minute_of_day"].map(expected_by_minute)
        current_rvol = current["cumulative_volume"] / current_expected.replace(0, np.nan)
        latest_rvol = self._latest_series_value(current_rvol)

        completed_five = five.copy()
        now = datetime.now(self.resolved_timezone)
        completed_mask = [
            now >= value.to_pydatetime() + timedelta(minutes=5)
            or current_day < now.date()
            for value in completed_five.index
        ]
        completed_volumes = completed_five.loc[completed_mask, "volume"]
        volume_acceleration = None
        if len(completed_volumes) >= 2:
            denominator_floor = max(
                float(completed_volumes.median()) * 0.10,
                1.0,
            )
            volume_acceleration = float(completed_volumes.iloc[-1]) / max(
                float(completed_volumes.iloc[-2]),
                denominator_floor,
            )

        fig, axes = plt.subplots(
            3,
            1,
            figsize=(16, 10),
            sharex=True,
            gridspec_kw={"height_ratios": [2.0, 1.35, 1.0]},
        )
        fig.patch.set_facecolor(self.COLORS["bg"])
        for axis in axes:
            self._style_evidence_axis(axis)

        five_times = five.index.tz_localize(None)
        bar_colors = np.where(
            five["close"].to_numpy() >= five["open"].to_numpy(),
            self.COLORS["candle_up"],
            self.COLORS["candle_down"],
        )
        axes[0].bar(
            five_times,
            five["volume"].to_numpy(dtype=float),
            width=4.2 / (24 * 60),
            color=bar_colors,
            alpha=0.82,
        )
        axes[0].set_ylabel("5m volume", color=self.COLORS["text_dim"])
        axes[0].set_title(
            f"{display_name} | VOLUME AND PARTICIPATION | DATA THROUGH {data_as_of.strftime('%H:%M IST')}",
            color=self.COLORS["text"],
            fontweight="bold",
            fontsize=14,
        )

        current_times = current["timestamp"].dt.tz_localize(None)
        axes[1].plot(
            current_times,
            current["cumulative_volume"],
            color=self.COLORS["ema9"],
            linewidth=1.8,
            label="Current cumulative volume",
        )
        if current_expected.notna().any():
            axes[1].plot(
                current_times,
                current_expected,
                color=self.COLORS["text_dim"],
                linewidth=1.4,
                linestyle="--",
                label="Prior-session same-time median",
            )
        axes[1].set_ylabel("Cumulative", color=self.COLORS["text_dim"])
        axes[1].legend(
            loc="upper left",
            facecolor=self.COLORS["bg"],
            edgecolor=self.COLORS["spine"],
            labelcolor=self.COLORS["text"],
        )

        axes[2].plot(
            current_times,
            current_rvol,
            color=self.COLORS["rsi_line"],
            linewidth=1.7,
            label="Time-of-day RVOL",
        )
        axes[2].axhline(1.0, color=self.COLORS["text_dim"], linestyle="--", linewidth=0.9)
        axes[2].set_ylabel("RVOL", color=self.COLORS["text_dim"])
        axes[2].set_xlabel("Time (IST)", color=self.COLORS["text_dim"])
        axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        suffix = "unavailable"
        if latest_rvol is not None:
            suffix = f"{latest_rvol:.2f}x"
        acceleration_text = (
            f"{volume_acceleration:.2f}x"
            if volume_acceleration is not None
            else "unavailable"
        )
        axes[2].text(
            0.99,
            0.90,
            f"Latest RVOL: {suffix} | Completed 5m acceleration: {acceleration_text}",
            transform=axes[2].transAxes,
            ha="right",
            va="top",
            color=self.COLORS["text"],
            fontsize=9,
        )
        plt.setp(axes[2].get_xticklabels(), rotation=30, ha="right")
        fig.tight_layout()
        fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor=self.COLORS["bg"])
        plt.close(fig)
        return {
            "source": "dhan_historical_ohlcv",
            "baseline_completed_sessions": int(prior["market_date"].nunique()),
            "time_of_day_rvol": round(latest_rvol, 3) if latest_rvol is not None else None,
            "completed_5m_volume_acceleration": (
                round(volume_acceleration, 3)
                if volume_acceleration is not None
                else None
            ),
            "trade_side_inference": False,
        }

    def _render_momentum_volatility_chart(
        self,
        *,
        local_frame: pd.DataFrame,
        display_name: str,
        market_date: str,
        data_as_of: pd.Timestamp,
        output_path: Path,
        **_: Any,
    ) -> Dict[str, Any]:
        """Render warm-started RSI and ATR% for the three current timeframes."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        fig, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True)
        fig.patch.set_facecolor(self.COLORS["bg"])
        for axis in axes:
            self._style_evidence_axis(axis)

        palette = {1: self.COLORS["ema9"], 5: self.COLORS["rsi_line"], 15: self.COLORS["ema21"]}
        latest: Dict[str, Any] = {}
        target_day = date.fromisoformat(market_date)
        for timeframe in self.CURRENT_DAY_TIMEFRAMES:
            resampled = self._resample_all_sessions(local_frame, timeframe)
            enriched = self._compute_warm_indicators(resampled)
            visible = enriched.loc[enriched.index.date == target_day].copy()
            if visible.empty:
                continue
            times = visible.index.tz_localize(None)
            color = palette[timeframe]
            axes[0].plot(
                times,
                visible["rsi"],
                color=color,
                linewidth=1.5,
                label=f"RSI(14) {timeframe}m",
            )
            axes[1].plot(
                times,
                visible["atr_percent"],
                color=color,
                linewidth=1.5,
                label=f"ATR(14)% {timeframe}m",
            )
            latest[str(timeframe)] = {
                "rsi": self._latest_series_value(visible["rsi"]),
                "atr": self._latest_series_value(visible["atr"]),
                "atr_percent": self._latest_series_value(visible["atr_percent"]),
            }

        axes[0].axhline(70, color=self.COLORS["rsi_ob"], linestyle="--", linewidth=0.9)
        axes[0].axhline(30, color=self.COLORS["rsi_os"], linestyle="--", linewidth=0.9)
        axes[0].axhline(50, color=self.COLORS["text_dim"], linestyle=":", linewidth=0.8)
        axes[0].set_ylim(0, 100)
        axes[0].set_ylabel("RSI(14)", color=self.COLORS["text_dim"])
        axes[0].set_title(
            f"{display_name} | MOMENTUM AND VOLATILITY | DATA THROUGH {data_as_of.strftime('%H:%M IST')}",
            color=self.COLORS["text"],
            fontweight="bold",
            fontsize=14,
        )
        axes[1].set_ylabel("ATR(14) % of close", color=self.COLORS["text_dim"])
        axes[1].set_xlabel("Time (IST)", color=self.COLORS["text_dim"])
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        for axis in axes:
            axis.legend(
                loc="upper left",
                facecolor=self.COLORS["bg"],
                edgecolor=self.COLORS["spine"],
                labelcolor=self.COLORS["text"],
                ncol=3,
            )
        plt.setp(axes[1].get_xticklabels(), rotation=30, ha="right")
        fig.tight_layout()
        fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor=self.COLORS["bg"])
        plt.close(fig)
        return {
            "source": "dhan_historical_ohlcv",
            "indicator_warmup_uses_prior_sessions": True,
            "latest": latest,
        }

    def _render_price_structure_liquidity_chart(
        self,
        *,
        today_frame: pd.DataFrame,
        display_name: str,
        market_date: str,
        data_as_of: pd.Timestamp,
        output_path: Path,
        prev_day_levels: Dict[str, float],
        **_: Any,
    ) -> Dict[str, Any]:
        """Render only OHLCV-observable structure and deterministic sweep events."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        frame = self._compute_full_indicators(self._resample_frame(today_frame, 5))
        if frame.empty:
            raise ValueError("No data for price-structure liquidity chart.")
        opening = frame.iloc[: min(3, len(frame))]
        references: List[Dict[str, Any]] = []
        if not opening.empty:
            references.extend(
                [
                    {"label": "ORH", "kind": "high", "price": float(opening["high"].max()), "available_index": len(opening) - 1},
                    {"label": "ORL", "kind": "low", "price": float(opening["low"].min()), "available_index": len(opening) - 1},
                ]
            )
        for key, label, kind in (
            ("prev_high", "PDH", "high"),
            ("prev_low", "PDL", "low"),
            ("prev_close", "PDC", "both"),
        ):
            if prev_day_levels.get(key) is not None:
                references.append(
                    {
                        "label": label,
                        "kind": kind,
                        "price": float(prev_day_levels[key]),
                        "available_index": 0,
                    }
                )

        highs = frame["high"].to_numpy(dtype=float)
        lows = frame["low"].to_numpy(dtype=float)
        atr = frame["atr"].to_numpy(dtype=float)
        confirmed_pivots: List[Dict[str, Any]] = []
        for index in range(2, len(frame) - 2):
            if highs[index] >= max(highs[index - 2:index + 3]):
                confirmed_pivots.append(
                    {
                        "kind": "high",
                        "price": float(highs[index]),
                        "available_index": index + 2,
                    }
                )
            if lows[index] <= min(lows[index - 2:index + 3]):
                confirmed_pivots.append(
                    {
                        "kind": "low",
                        "price": float(lows[index]),
                        "available_index": index + 2,
                    }
                )

        latest_atr = self._latest_finite(frame, "atr")
        tolerance = max(float(frame["close"].iloc[-1]) * 0.0005, latest_atr * 0.12, 0.05)
        pools: List[Dict[str, Any]] = []
        for kind in ("high", "low"):
            pivots = [item for item in confirmed_pivots if item["kind"] == kind]
            used: set[int] = set()
            for index, pivot in enumerate(pivots):
                if index in used:
                    continue
                cluster = [
                    (other_index, other)
                    for other_index, other in enumerate(pivots)
                    if abs(other["price"] - pivot["price"]) <= tolerance
                ]
                if len(cluster) >= 2:
                    used.update(item[0] for item in cluster)
                    pools.append(
                        {
                            "label": "EQUAL HIGHS" if kind == "high" else "EQUAL LOWS",
                            "kind": kind,
                            "price": float(np.mean([item[1]["price"] for item in cluster])),
                            "available_index": max(item[1]["available_index"] for item in cluster),
                            "touches": len(cluster),
                        }
                    )

        sweep_references = references + pools
        sweeps: List[Dict[str, Any]] = []
        completed_limit = len(frame)
        now = datetime.now(self.resolved_timezone)
        if date.fromisoformat(market_date) == now.date() and frame.index[-1].to_pydatetime() + timedelta(minutes=5) > now:
            completed_limit -= 1
        for reference in sweep_references:
            price = float(reference["price"])
            for index in range(int(reference["available_index"]) + 1, completed_limit):
                buffer = max(0.05, (atr[index] if math.isfinite(atr[index]) else latest_atr) * 0.05)
                row = frame.iloc[index]
                if (
                    reference.get("kind") in {"high", "both"}
                    and float(row["high"]) >= price + buffer
                    and float(row["close"]) < price
                ):
                    sweeps.append({"index": index, "side": "high", "price": price, "label": reference["label"]})
                    break
                if (
                    reference.get("kind") in {"low", "both"}
                    and float(row["low"]) <= price - buffer
                    and float(row["close"]) > price
                ):
                    sweeps.append({"index": index, "side": "low", "price": price, "label": reference["label"]})
                    break

        plot = frame.iloc[-90:].copy()
        offset = len(frame) - len(plot)
        x = np.arange(len(plot))
        span = max(float(plot["high"].max() - plot["low"].min()), 0.01)
        y_padding = max(span * 0.08, latest_atr * 0.35, 0.05)
        y_min = float(plot["low"].min()) - y_padding
        y_max = float(plot["high"].max()) + y_padding
        fig, axis = plt.subplots(figsize=(16, 9))
        fig.patch.set_facecolor(self.COLORS["bg"])
        self._style_evidence_axis(axis)
        for local_index, (_, row) in enumerate(plot.iterrows()):
            up = float(row["close"]) >= float(row["open"])
            color = self.COLORS["candle_up"] if up else self.COLORS["candle_down"]
            axis.vlines(local_index, row["low"], row["high"], color=color, linewidth=1.2)
            bottom = min(float(row["open"]), float(row["close"]))
            height = max(abs(float(row["close"]) - float(row["open"])), span * 0.0015)
            axis.add_patch(Rectangle((local_index - 0.31, bottom), 0.62, height, color=color, alpha=0.9))

        line_specs = references + pools
        offscreen: List[str] = []
        for reference in line_specs:
            price = float(reference["price"])
            if not y_min <= price <= y_max:
                direction = "↑" if price > y_max else "↓"
                offscreen.append(f"{direction} {reference['label']} {price:.2f}")
                continue
            color = (
                self.COLORS["rsi_line"]
                if reference["label"] in {"ORH", "ORL"}
                else self.COLORS["ema21"]
                if reference["label"].startswith("EQUAL")
                else self.COLORS["text_dim"]
            )
            axis.axhline(price, color=color, linestyle="--", linewidth=1.0, alpha=0.75)
            axis.text(
                len(plot) - 0.2,
                price,
                f"{reference['label']} {price:.2f}",
                color=color,
                ha="right",
                va="bottom",
                fontsize=8,
            )
        for sweep in sweeps:
            local_index = int(sweep["index"]) - offset
            if 0 <= local_index < len(plot):
                marker = "v" if sweep["side"] == "high" else "^"
                y = float(plot.iloc[local_index]["high" if sweep["side"] == "high" else "low"])
                axis.scatter(
                    [local_index],
                    [y],
                    marker=marker,
                    s=80,
                    color=self.COLORS["rsi_line"],
                    edgecolor=self.COLORS["text"],
                    zorder=8,
                )
                axis.annotate(
                    f"{sweep['label']} SWEEP",
                    (local_index, y),
                    xytext=(0, 15 if sweep["side"] == "high" else -20),
                    textcoords="offset points",
                    ha="center",
                    color=self.COLORS["text"],
                    fontsize=8,
                )
        tick_step = max(1, len(plot) // 10)
        ticks = np.arange(0, len(plot), tick_step)
        axis.set_xticks(ticks)
        axis.set_xticklabels([plot.index[value].strftime("%H:%M") for value in ticks], rotation=30, ha="right")
        axis.set_xlim(-1, len(plot) + 1)
        axis.set_ylim(y_min, y_max)
        axis.set_ylabel("Price (₹)", color=self.COLORS["text_dim"])
        axis.set_xlabel("Time (IST)", color=self.COLORS["text_dim"])
        axis.set_title(
            (
                f"{display_name} | PRICE-STRUCTURE LIQUIDITY MAP — OHLCV DERIVED | "
                f"DATA THROUGH {data_as_of.strftime('%H:%M IST')}"
            ),
            color=self.COLORS["text"],
            fontweight="bold",
            fontsize=14,
        )
        if offscreen:
            axis.text(
                0.99,
                0.02,
                "  |  ".join(offscreen),
                transform=axis.transAxes,
                ha="right",
                va="bottom",
                color=self.COLORS["text_dim"],
                fontsize=8,
            )
        fig.tight_layout()
        fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor=self.COLORS["bg"])
        plt.close(fig)
        return {
            "source": "dhan_historical_ohlcv",
            "order_book_data": False,
            "equal_high_low_pools": len(pools),
            "confirmed_sweeps": len(sweeps),
            "sweep_requires_completed_candle": True,
        }

    def _render_tpo_profile_chart(
        self,
        *,
        today_frame: pd.DataFrame,
        previous_frame: pd.DataFrame,
        display_name: str,
        market_date: str,
        previous_market_date: str,
        data_as_of: pd.Timestamp,
        output_path: Path,
        **_: Any,
    ) -> Dict[str, Any]:
        """Render TPO time-at-price profiles; no volume-at-price is invented."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        current_profile = self._build_tpo_profile(today_frame)
        previous_profile = self._build_tpo_profile(previous_frame)
        fig, axes = plt.subplots(1, 2, figsize=(16, 9))
        fig.patch.set_facecolor(self.COLORS["bg"])
        for axis in axes:
            self._style_evidence_axis(axis)
        self._plot_tpo_profile(
            axes[0],
            current_profile,
            f"CURRENT {market_date} · THROUGH {data_as_of.strftime('%H:%M IST')}",
            self.COLORS["ema9"],
        )
        self._plot_tpo_profile(
            axes[1],
            previous_profile,
            f"PREVIOUS {previous_market_date}",
            self.COLORS["ema21"],
        )
        fig.suptitle(
            f"{display_name} | TPO MARKET PROFILE — TIME AT PRICE, NOT VOLUME AT PRICE",
            color=self.COLORS["text"],
            fontweight="bold",
            fontsize=14,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor=self.COLORS["bg"])
        plt.close(fig)
        return {
            "source": "dhan_historical_ohlcv",
            "profile_type": "tpo_time_at_price",
            "volume_at_price": False,
            "current": self._profile_metadata(current_profile),
            "previous": self._profile_metadata(previous_profile),
        }

    def _resample_all_sessions(
        self,
        local_frame: pd.DataFrame,
        timeframe_minutes: int,
    ) -> pd.DataFrame:
        if local_frame.empty:
            return pd.DataFrame()
        sessions: List[pd.DataFrame] = []
        for _, session in local_frame.groupby(local_frame["timestamp"].dt.date, sort=True):
            indexed = session.set_index("timestamp")
            resampled = (
                indexed[["open", "high", "low", "close", "volume"]]
                .resample(f"{timeframe_minutes}min", label="left", closed="left")
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )
                .dropna(subset=["open", "high", "low", "close"])
            )
            sessions.append(resampled)
        return pd.concat(sessions).sort_index() if sessions else pd.DataFrame()

    def _compute_warm_indicators(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        enriched = frame.copy()
        delta = enriched["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        enriched["rsi"] = 100 - (100 / (1 + rs))
        true_range = pd.concat(
            [
                enriched["high"] - enriched["low"],
                (enriched["high"] - enriched["close"].shift(1)).abs(),
                (enriched["low"] - enriched["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        enriched["atr"] = true_range.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        enriched["atr_percent"] = enriched["atr"] / enriched["close"].replace(0, np.nan) * 100
        return enriched

    def _build_tpo_profile(self, frame: pd.DataFrame) -> Dict[str, Any]:
        if frame.empty:
            return {}
        low = float(frame["low"].min())
        high = float(frame["high"].max())
        span = max(high - low, 0.05)
        raw_row_size = max(0.05, span / 80.0)
        row_size = math.ceil(raw_row_size / 0.05) * 0.05
        rows = np.arange(
            math.floor(low / row_size) * row_size,
            math.ceil(high / row_size) * row_size + row_size / 2,
            row_size,
        )
        counts = np.zeros(len(rows), dtype=int)
        letters: List[List[str]] = [[] for _ in rows]
        brackets = list(frame.groupby(frame.index.floor("30min"), sort=True))
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        for bracket_index, (_, bracket) in enumerate(brackets):
            bracket_low = float(bracket["low"].min())
            bracket_high = float(bracket["high"].max())
            mask = (rows >= bracket_low - row_size / 2) & (rows <= bracket_high + row_size / 2)
            label = alphabet[bracket_index % len(alphabet)]
            for row_index in np.flatnonzero(mask):
                counts[row_index] += 1
                letters[row_index].append(label)
        if not counts.any():
            return {}
        poc_index = int(np.argmax(counts))
        target = int(math.ceil(counts.sum() * 0.70))
        included = {poc_index}
        total = int(counts[poc_index])
        lower = poc_index - 1
        upper = poc_index + 1
        while total < target and (lower >= 0 or upper < len(counts)):
            lower_count = int(counts[lower]) if lower >= 0 else -1
            upper_count = int(counts[upper]) if upper < len(counts) else -1
            chosen = upper if upper_count >= lower_count else lower
            included.add(chosen)
            total += int(counts[chosen])
            if chosen == upper:
                upper += 1
            else:
                lower -= 1
        session_start = frame.index.min().replace(
            hour=self.market_open[0],
            minute=self.market_open[1],
            second=0,
            microsecond=0,
        )
        initial_balance = frame.loc[
            (frame.index >= session_start)
            & (frame.index < session_start + pd.Timedelta(minutes=60))
        ]
        if initial_balance.empty:
            initial_balance = frame.iloc[:1]
        return {
            "rows": rows,
            "counts": counts,
            "letters": ["".join(value) for value in letters],
            "row_size": row_size,
            "poc": float(rows[poc_index]),
            "vah": float(rows[max(included)]),
            "val": float(rows[min(included)]),
            "initial_balance_high": float(initial_balance["high"].max()),
            "initial_balance_low": float(initial_balance["low"].min()),
            "brackets": len(brackets),
        }

    def _plot_tpo_profile(
        self,
        axis: Any,
        profile: Dict[str, Any],
        title: str,
        color: str,
    ) -> None:
        axis.set_title(title, color=self.COLORS["text"], fontweight="bold")
        if not profile:
            axis.text(
                0.5,
                0.5,
                "PROFILE UNAVAILABLE",
                transform=axis.transAxes,
                ha="center",
                va="center",
                color=self.COLORS["text_dim"],
            )
            return
        rows = profile["rows"]
        counts = profile["counts"]
        axis.barh(rows, counts, height=profile["row_size"] * 0.82, color=color, alpha=0.68)
        for row, letters in zip(rows, profile["letters"]):
            if letters:
                axis.text(0.1, row, letters, va="center", color=self.COLORS["text"], fontsize=6)
        for key, label, line_color in (
            ("poc", "TPO POC", self.COLORS["rsi_line"]),
            ("vah", "VAH", self.COLORS["candle_up"]),
            ("val", "VAL", self.COLORS["candle_down"]),
            ("initial_balance_high", "IBH", self.COLORS["text_dim"]),
            ("initial_balance_low", "IBL", self.COLORS["text_dim"]),
        ):
            value = float(profile[key])
            axis.axhline(value, color=line_color, linestyle="--", linewidth=1.0)
            axis.text(max(counts) * 0.98, value, f"{label} {value:.2f}", ha="right", va="bottom", color=line_color, fontsize=8)
        axis.set_xlabel("TPO count", color=self.COLORS["text_dim"])
        axis.set_ylabel("Price (₹)", color=self.COLORS["text_dim"])

    @staticmethod
    def _profile_metadata(profile: Dict[str, Any]) -> Dict[str, Any]:
        if not profile:
            return {"status": "unavailable"}
        return {
            "status": "available",
            "row_size": round(float(profile["row_size"]), 4),
            "poc": round(float(profile["poc"]), 4),
            "vah": round(float(profile["vah"]), 4),
            "val": round(float(profile["val"]), 4),
            "initial_balance_high": round(float(profile["initial_balance_high"]), 4),
            "initial_balance_low": round(float(profile["initial_balance_low"]), 4),
            "brackets": int(profile["brackets"]),
        }

    def _style_evidence_axis(self, axis: Any) -> None:
        axis.set_facecolor(self.COLORS["panel_bg"])
        axis.grid(color=self.COLORS["grid"], linestyle="--", linewidth=0.5, alpha=0.45)
        axis.tick_params(colors=self.COLORS["text_dim"], labelsize=9)
        for spine in axis.spines.values():
            spine.set_color(self.COLORS["spine"])

    @staticmethod
    def _latest_series_value(series: pd.Series) -> Optional[float]:
        values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            return None
        return float(values.iloc[-1])

    def _latest_finite(self, frame: pd.DataFrame, column: str) -> float:
        if column not in frame.columns:
            return 0.0
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            return 0.0
        value = float(values.iloc[-1])
        return value if math.isfinite(value) else 0.0

    def _render_chart_legacy(
        self,
        frame: pd.DataFrame,
        title: str,
        subtitle: str,
        output_path: Path,
        market_date: str,
        timeframe_minutes: int,
        sr_levels: List[Dict[str, Any]],
        sd_zones: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        prev_day_levels: Dict[str, float],
    ) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        from matplotlib.ticker import FuncFormatter

        if frame.empty:
            raise ValueError(f"Cannot render empty chart for {title}.")

        C = self.COLORS

        # 4-panel layout: Price, Volume, RSI, CVD
        fig, (ax_price, ax_volume, ax_rsi, ax_cvd) = plt.subplots(
            4, 1,
            figsize=(14, 13),
            sharex=True,
            gridspec_kw={"height_ratios": [5, 1, 1.2, 1.2], "hspace": 0.05},
        )
        fig.patch.set_facecolor(C["bg"])
        for ax in (ax_price, ax_volume, ax_rsi, ax_cvd):
            ax.set_facecolor(C["panel_bg"])

        # ── 1m chart special handling: slice to last 2 hours (120 candles) ──
        # 1m on full session (375 candles) crushes candle width to ~3px.
        # Showing only the last 2 hours keeps each candle visible while preserving
        # the most relevant intraday context for trade decisions.
        plot_frame = frame.copy()
        if timeframe_minutes == 1 and len(plot_frame) > 120:
            plot_frame = plot_frame.iloc[-120:]
        if plot_frame.index.tz is not None:
            plot_frame.index = plot_frame.index.tz_localize(None)

        n_candles = len(plot_frame)
        x_positions = np.arange(n_candles, dtype=float)
        timestamps = plot_frame.index.to_pydatetime()
        candle_width = 0.78  # Fixed body width — looks great at any timeframe

        # ── Compute full session expected candles (for non-1m x-axis extent) ──
        # For 1m we don't extend; for other timeframes we extend to show the full session
        # so the LLM sees how much of the day remains.
        market_day = pd.Timestamp(market_date).date()
        session_start = pd.Timestamp(
            year=market_day.year, month=market_day.month, day=market_day.day,
            hour=self.market_open[0], minute=self.market_open[1],
        )
        session_end = pd.Timestamp(
            year=market_day.year, month=market_day.month, day=market_day.day,
            hour=self.market_close[0], minute=self.market_close[1],
        )
        tf_minutes = timeframe_minutes
        total_session_minutes = int((session_end - session_start).total_seconds() / 60)
        full_session_candles = total_session_minutes // max(tf_minutes, 1)

        # ── Draw Candlesticks ──
        for idx in range(n_candles):
            row = plot_frame.iloc[idx]
            x = x_positions[idx]
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            vol = float(row["volume"])
            is_up = c >= o

            face = C["candle_up"] if is_up else C["candle_down"]
            edge = C["candle_up_edge"] if is_up else C["candle_down_edge"]
            wick = C["wick_up"] if is_up else C["wick_down"]

            # Wick
            ax_price.vlines(x, l, h, color=wick, linewidth=1.6, zorder=3)

            # Body — with minimum height for visibility (especially dojis)
            body_low = min(o, c)
            price_range = max(h - l, 0.001)
            body_height = max(abs(c - o), price_range * 0.05)
            ax_price.add_patch(
                Rectangle(
                    (x - candle_width / 2, body_low),
                    candle_width,
                    body_height,
                    facecolor=face,
                    edgecolor=edge,
                    linewidth=0.9,
                    zorder=4,
                )
            )

            # Volume bars
            ax_volume.bar(x, vol, width=candle_width, color=face, alpha=0.85, edgecolor=edge, linewidth=0.4)

        # ── Supply & Demand Zones ──
        # x_right is set after we determine the chart's x-extent below.
        is_compact_view = timeframe_minutes == 1
        if is_compact_view:
            x_right = n_candles - 1 + max(int(n_candles * 0.10), 3)
        else:
            x_right = full_session_candles
        for zone in sd_zones:
            alpha = 0.20 if zone["strength"] == "strong" else 0.12
            color = C["sd_demand"] if zone["type"] == "demand" else C["sd_supply"]
            ax_price.axhspan(zone["zone_low"], zone["zone_high"], alpha=alpha, color=color, zorder=0)

            # Label on the right side (inside the empty future-session space) so it doesn't clash with candles
            label_y = (zone["zone_high"] + zone["zone_low"]) / 2
            label_text = f"{'SUPPLY' if zone['type'] == 'supply' else 'DEMAND'} ZONE"
            ax_price.text(
                x_right - 0.3, label_y, label_text,
                fontsize=8, color=color, alpha=0.95, va="center", ha="right",
                fontweight="bold", zorder=5,
            )

        # ── Support & Resistance Lines ──
        for level in sr_levels:
            color = C["sr_support"] if level["type"] == "support" else C["sr_resistance"]
            style = "--" if level["source"] == "pivot" else "-."
            ax_price.axhline(level["price"], color=color, linestyle=style, linewidth=0.9, alpha=0.55, zorder=1)

        # ── Previous Day Levels (labels on right edge) ──
        if prev_day_levels:
            ph = prev_day_levels.get("prev_high")
            pl = prev_day_levels.get("prev_low")
            pc = prev_day_levels.get("prev_close")
            if ph:
                ax_price.axhline(ph, color=C["prev_high"], linestyle=":", linewidth=1.0, alpha=0.75, zorder=1)
                ax_price.text(x_right - 0.5, ph, f" PDH {ph:.1f}", fontsize=8, color=C["prev_high"], va="bottom", ha="right", zorder=5, fontweight="bold")
            if pl:
                ax_price.axhline(pl, color=C["prev_low"], linestyle=":", linewidth=1.0, alpha=0.75, zorder=1)
                ax_price.text(x_right - 0.5, pl, f" PDL {pl:.1f}", fontsize=8, color=C["prev_low"], va="top", ha="right", zorder=5, fontweight="bold")
            if pc:
                ax_price.axhline(pc, color=C["prev_close"], linestyle=":", linewidth=1.0, alpha=0.75, zorder=1)
                ax_price.text(x_right - 0.5, pc, f" PDC {pc:.1f}", fontsize=8, color=C["prev_close"], va="bottom", ha="right", zorder=5, fontweight="bold")

        # ── EMA 9/21 Overlay (use only valid x positions) ──
        if "ema9" in plot_frame.columns and not plot_frame["ema9"].isna().all():
            ax_price.plot(x_positions, plot_frame["ema9"].values, color=C["ema9"], linewidth=1.5, label="EMA9", zorder=5)
        if "ema21" in plot_frame.columns and not plot_frame["ema21"].isna().all():
            ax_price.plot(x_positions, plot_frame["ema21"].values, color=C["ema21"], linewidth=1.5, label="EMA21", zorder=5)

        # ── Bollinger Bands ──
        if "bb_upper" in plot_frame.columns and not plot_frame["bb_upper"].isna().all():
            ax_price.plot(x_positions, plot_frame["bb_upper"].values, color=C["bb_line"], linewidth=0.8, alpha=0.55, zorder=2)
            ax_price.plot(x_positions, plot_frame["bb_lower"].values, color=C["bb_line"], linewidth=0.8, alpha=0.55, zorder=2)
            ax_price.fill_between(
                x_positions, plot_frame["bb_upper"].values, plot_frame["bb_lower"].values,
                color=C["bb_fill"], alpha=0.07, zorder=0,
            )

        # ── VWAP ──
        if "vwap" in plot_frame.columns and not plot_frame["vwap"].isna().all():
            ax_price.plot(x_positions, plot_frame["vwap"].values, color=C["vwap"], linewidth=2.2, label="VWAP", zorder=6)

        # ── Candlestick Pattern Annotations ──
        # Filter to avoid clutter: keep at most 4 patterns, prefer non-Doji and recent ones
        atr_series = plot_frame["atr"].values if "atr" in plot_frame.columns else np.full(n_candles, 1.0)
        price_span = float(plot_frame["high"].max() - plot_frame["low"].min())
        offset_base = max(price_span * 0.04, 0.8)

        # Sort patterns: prefer engulfing/hammer/shooting star over doji, then by recency
        pattern_priority = {"Bull Engulf": 0, "Bear Engulf": 0, "Hammer": 1, "Shooting Star": 1, "Doji": 2}
        sorted_patterns = sorted(
            patterns,
            key=lambda p: (pattern_priority.get(p["pattern"], 3), -p["index"]),
        )[:4]

        for pat_idx, pat in enumerate(sorted_patterns):
            idx = pat["index"]
            if idx >= n_candles:
                continue
            x = x_positions[idx]
            price = pat["price"]
            color = C["pattern_bull"] if pat["bias"] == "bullish" else C["pattern_bear"]
            marker = "^" if pat["bias"] == "bullish" else "v"

            # Stagger annotations vertically to avoid overlap when patterns are clustered
            stagger_offset = offset_base * (1.0 + (pat_idx % 2) * 0.6)
            y = price - stagger_offset if pat["bias"] == "bullish" else price + stagger_offset

            ax_price.scatter(x, y, marker=marker, color=color, s=100, zorder=7, edgecolors="white", linewidths=0.8)
            label_y_offset = -22 if pat["bias"] == "bullish" else 22
            ax_price.annotate(
                pat["pattern"], xy=(x, y),
                xytext=(0, label_y_offset),
                textcoords="offset points",
                fontsize=8, color=color, ha="center",
                va="top" if pat["bias"] == "bullish" else "bottom",
                fontweight="bold",
                zorder=7,
                bbox=dict(boxstyle="round,pad=0.2", facecolor=C["bg"], edgecolor=color, alpha=0.85, linewidth=0.5),
            )

        # ── RSI Panel ──
        if "rsi" in plot_frame.columns and not plot_frame["rsi"].isna().all():
            ax_rsi.plot(x_positions, plot_frame["rsi"].values, color=C["rsi_line"], linewidth=1.6)
            ax_rsi.axhline(70, color=C["rsi_ob"], linestyle="--", linewidth=0.8, alpha=0.7)
            ax_rsi.axhline(30, color=C["rsi_os"], linestyle="--", linewidth=0.8, alpha=0.7)
            ax_rsi.axhline(50, color=C["rsi_mid"], linestyle=":", linewidth=0.6, alpha=0.5)
            ax_rsi.fill_between(x_positions, plot_frame["rsi"].values, 70, where=(plot_frame["rsi"].values >= 70), color=C["rsi_ob"], alpha=0.18)
            ax_rsi.fill_between(x_positions, plot_frame["rsi"].values, 30, where=(plot_frame["rsi"].values <= 30), color=C["rsi_os"], alpha=0.18)
            ax_rsi.set_ylim(0, 100)
            ax_rsi.set_ylabel("RSI", color=C["text_dim"], fontsize=10)

        # ── CVD Panel ──
        if "cvd" in plot_frame.columns and not plot_frame["cvd"].isna().all():
            cvd_vals = plot_frame["cvd"].values
            ax_cvd.plot(x_positions, cvd_vals, color=C["cvd_pos"], linewidth=1.6)
            ax_cvd.fill_between(x_positions, cvd_vals, 0, where=(cvd_vals >= 0), color=C["cvd_pos"], alpha=0.25, interpolate=True)
            ax_cvd.fill_between(x_positions, cvd_vals, 0, where=(cvd_vals < 0), color=C["cvd_neg"], alpha=0.25, interpolate=True)
            ax_cvd.axhline(0, color=C["spine"], linestyle="--", linewidth=0.8)

        # ── X-axis: index-based with time-formatted ticks ──
        # Build mapping from index → timestamp for the formatter
        index_to_time = {i: timestamps[i] for i in range(n_candles)}

        def format_time(x_val: float, _pos: int) -> str:
            idx = int(round(x_val))
            if 0 <= idx < n_candles:
                return index_to_time[idx].strftime("%H:%M")
            # Extrapolate for empty future candles
            if idx >= n_candles and n_candles >= 1:
                last_ts = timestamps[-1]
                projected = last_ts + timedelta(minutes=tf_minutes * (idx - n_candles + 1))
                # Don't show times past market close
                if projected > session_end:
                    return ""
                return projected.strftime("%H:%M")
            return ""

        ax_cvd.xaxis.set_major_formatter(FuncFormatter(format_time))

        # ── X-axis extent and ticks ──
        # 1m: compact view (last ~120 candles + small padding) so candles stay readable.
        # All other timeframes: extend to full session so the LLM sees how much
        # of the trading day has elapsed vs. how much remains.
        if is_compact_view:
            x_left_lim = -0.8
            x_right_lim = n_candles - 1 + max(int(n_candles * 0.10), 3)
            tick_count = 10
            tick_step = max(1, n_candles // tick_count)
            ax_cvd.set_xticks(np.arange(0, n_candles, tick_step))
        else:
            x_left_lim = -0.8
            x_right_lim = full_session_candles + 0.5
            tick_count = 12
            tick_step = max(1, full_session_candles // tick_count)
            ax_cvd.set_xticks(np.arange(0, full_session_candles + 1, tick_step))

        ax_price.set_xlim(x_left_lim, x_right_lim)

        # ── Y-axis: tighten price panel to actual price range with padding ──
        price_min = float(plot_frame["low"].min())
        price_max = float(plot_frame["high"].max())
        # Include S/R, S/D zones, prev day levels in y-range so they're visible
        all_y = [price_min, price_max]
        for level in sr_levels:
            all_y.append(level["price"])
        for zone in sd_zones:
            all_y.extend([zone["zone_low"], zone["zone_high"]])
        if prev_day_levels:
            all_y.extend([v for v in prev_day_levels.values() if v])
        y_min, y_max = min(all_y), max(all_y)
        y_pad = max((y_max - y_min) * 0.08, 0.5)
        ax_price.set_ylim(y_min - y_pad, y_max + y_pad)

        # ── Legend ──
        ax_price.legend(
            loc="upper left", facecolor=C["bg"], edgecolor=C["spine"],
            labelcolor=C["text"], fontsize=9, framealpha=0.92,
        )

        # ── Title ──
        latest_vwap = plot_frame["vwap"].iloc[-1] if "vwap" in plot_frame.columns and not plot_frame["vwap"].isna().all() else 0.0
        latest_atr = plot_frame["atr"].iloc[-1] if "atr" in plot_frame.columns and not plot_frame["atr"].isna().all() else 0.0
        latest_rsi = plot_frame["rsi"].iloc[-1] if "rsi" in plot_frame.columns and not plot_frame["rsi"].isna().all() else 0.0

        full_title = f"{title} | VWAP: \u20b9{latest_vwap:.2f} | ATR(14): \u20b9{latest_atr:.2f} | RSI: {latest_rsi:.0f}"
        ax_price.set_title(full_title, color=C["text"], fontsize=13, pad=10, fontweight="bold")
        fig.suptitle(subtitle, color="#82aaff", fontsize=11, fontweight="bold", y=0.995)

        # ── Styling ──
        for ax in (ax_price, ax_volume, ax_rsi, ax_cvd):
            ax.grid(color=C["grid"], linestyle="--", linewidth=0.5, alpha=0.5)
            ax.tick_params(colors=C["text_dim"], labelsize=9)
            for spine in ax.spines.values():
                spine.set_color(C["spine"])

        ax_price.set_ylabel("Price (\u20b9)", color=C["text_dim"], fontsize=10)
        ax_volume.set_ylabel("Vol", color=C["text_dim"], fontsize=10)
        ax_cvd.set_ylabel("CVD", color=C["text_dim"], fontsize=10)

        # Rotate x-axis tick labels for readability
        plt.setp(ax_cvd.get_xticklabels(), rotation=45, ha="right")

        plt.subplots_adjust(left=0.07, right=0.98, top=0.95, bottom=0.07, hspace=0.05)
        fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor=C["bg"])
        plt.close(fig)

    # ─── UTILITIES ─────────────────────────────────────────────────────────

    def _candle_width(self, date_numbers: Any) -> float:
        if len(date_numbers) < 2:
            return 0.003
        diffs = [abs(date_numbers[idx] - date_numbers[idx - 1]) for idx in range(1, len(date_numbers))]
        median = sorted(diffs)[len(diffs) // 2] if diffs else 0.003
        return max(median * 0.82, 0.0018)

    def _previous_trading_day(self, market_date_str: str) -> date:
        current = date.fromisoformat(market_date_str)
        prev = current - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        return prev

    def _timeframe_label(self, minutes: int) -> str:
        if minutes >= 60:
            return f"{minutes // 60}h"
        return f"{minutes}m"

    def _to_market_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        local_frame = frame.copy()
        local_frame["timestamp"] = (
            pd.to_datetime(local_frame["timestamp"], errors="coerce", utc=True)
            .dt.tz_convert(self.resolved_timezone)
        )
        local_frame = local_frame.dropna(subset=["timestamp"]).sort_values("timestamp")
        return local_frame

    def _day_frame(self, frame: pd.DataFrame, market_date_str: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        market_day = pd.Timestamp(market_date_str).date()
        filtered = frame[frame["timestamp"].dt.date == market_day].copy()
        if filtered.empty:
            return filtered
        return filtered.set_index("timestamp")

    def _slugify(self, value: str) -> str:
        compact = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
        return compact or "stock"

    def _resolve_timezone(self, timezone_name: str):
        aliases = [timezone_name]
        if timezone_name == "Asia/Calcutta":
            aliases.append("Asia/Kolkata")
        for alias in aliases:
            try:
                return ZoneInfo(alias)
            except ZoneInfoNotFoundError:
                continue
        return timezone_name
