from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CandlestickChartService:
    """Generates professional candlestick chart images optimized for LLM vision analysis.

    Charts include: Price (candlesticks + EMA9/21 + Bollinger Bands + VWAP + S/R + S/D zones),
    Volume, RSI(14), and CVD panels. Full trading session x-axis (9:15-15:30).
    """

    CURRENT_DAY_TIMEFRAMES: List[int] = [1, 5, 15, 30, 60]
    PREVIOUS_DAY_TIMEFRAMES: List[int] = [5, 15, 60]

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

        # Get previous day frame for S/R computation
        prev_date = self._previous_trading_day(market_date)
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
                subtitle=f"CURRENT DAY \u2014 {market_date}",
                output_path=path,
                market_date=market_date,
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
                "date": market_date,
                "path": str(path),
                "candles": int(len(resampled)),
            }
            chart_paths_ordered.append(str(path))

            # Store metadata for the primary analysis timeframe (5m)
            if timeframe == 5:
                technical_metadata = self._build_technical_metadata(
                    enriched, sr_levels, sd_zones, patterns, prev_day_levels
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
                    "date": prev_date_str,
                    "path": str(path),
                    "candles": int(len(resampled)),
                }
                chart_paths_ordered.append(str(path))

        return {
            "market_date": market_date,
            "previous_market_date": prev_date_str if not prev_frame.empty else None,
            "chart_count": len(charts),
            "charts": charts,
            "chart_paths_ordered": chart_paths_ordered,
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
        df["rsi"] = df["rsi"].fillna(50)

        # Backfill Bollinger Bands for early candles
        df["bb_mid"] = df["bb_mid"].bfill()
        df["bb_upper"] = df["bb_upper"].bfill()
        df["bb_lower"] = df["bb_lower"].bfill()

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

        # Only keep the last 5 most recent patterns to avoid clutter
        return patterns[-5:]

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
        meta["cvd_direction"] = "positive" if "cvd" in frame.columns and float(last.get("cvd", 0)) > 0 else "negative"

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
            df[["open", "high", "low", "close", "volume", "vwap", "cvd"]]
            .resample(rule, label="left", closed="left")
            .agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "vwap": "last",
                "cvd": "last",
            })
            .dropna(subset=["open", "high", "low", "close"])
        )

        # ATR (14)
        high_low = ohlcv["high"] - ohlcv["low"]
        high_close_prev = (ohlcv["high"] - ohlcv["close"].shift(1)).abs()
        low_close_prev = (ohlcv["low"] - ohlcv["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        ohlcv["atr"] = true_range.rolling(window=14).mean()
        ohlcv["atr"] = ohlcv["atr"].bfill()

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

        # CVD
        df["delta"] = df["volume"]
        df.loc[df["close"] < df["open"], "delta"] = -df["volume"]
        df["cvd"] = df["delta"].cumsum()

        return df

    # ─── CHART RENDERING ───────────────────────────────────────────────────

    def _render_chart(
        self,
        frame: pd.DataFrame,
        title: str,
        subtitle: str,
        output_path: Path,
        market_date: str,
        sr_levels: List[Dict[str, Any]],
        sd_zones: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        prev_day_levels: Dict[str, float],
    ) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch, Rectangle

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

        # Timezone-naive for matplotlib
        plot_frame = frame.copy()
        if plot_frame.index.tz is not None:
            plot_frame.index = plot_frame.index.tz_localize(None)

        date_numbers = mdates.date2num(plot_frame.index.to_pydatetime())
        candle_width = self._candle_width(date_numbers)

        # ── Draw Candlesticks ──
        for idx, (_, row) in enumerate(plot_frame.iterrows()):
            x = date_numbers[idx]
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            vol = float(row["volume"])
            is_up = c >= o

            face = C["candle_up"] if is_up else C["candle_down"]
            edge = C["candle_up_edge"] if is_up else C["candle_down_edge"]
            wick = C["wick_up"] if is_up else C["wick_down"]

            # Wick (shadow)
            ax_price.vlines(x, l, h, color=wick, linewidth=1.6, zorder=2)

            # Body
            body_low = min(o, c)
            body_height = max(abs(c - o), (h - l) * 0.02)  # Minimum visible body
            ax_price.add_patch(
                Rectangle(
                    (x - candle_width / 2, body_low),
                    candle_width,
                    body_height,
                    facecolor=face,
                    edgecolor=edge,
                    linewidth=0.8,
                    zorder=3,
                )
            )

            # Volume bars
            ax_volume.bar(x, vol, width=candle_width, color=face, alpha=0.85, edgecolor=edge, linewidth=0.3)

        # ── Supply & Demand Zones (draw BEHIND candles via zorder) ──
        for zone in sd_zones:
            alpha = 0.18 if zone["strength"] == "strong" else 0.10
            color = C["sd_demand"] if zone["type"] == "demand" else C["sd_supply"]
            ax_price.axhspan(
                zone["zone_low"], zone["zone_high"],
                alpha=alpha, color=color, zorder=0,
            )
            # Label
            label_y = zone["zone_high"] if zone["type"] == "supply" else zone["zone_low"]
            label_text = f"{'Supply' if zone['type'] == 'supply' else 'Demand'} Zone"
            ax_price.text(
                date_numbers[0], label_y, f" {label_text}",
                fontsize=7, color=color, alpha=0.8, va="bottom" if zone["type"] == "demand" else "top",
                zorder=5,
            )

        # ── Support & Resistance Lines ──
        for level in sr_levels:
            color = C["sr_support"] if level["type"] == "support" else C["sr_resistance"]
            style = "--" if level["source"] == "pivot" else "-."
            ax_price.axhline(
                level["price"], color=color, linestyle=style,
                linewidth=0.9, alpha=0.6, zorder=1,
            )

        # ── Previous Day Levels ──
        if prev_day_levels:
            ph = prev_day_levels.get("prev_high")
            pl = prev_day_levels.get("prev_low")
            pc = prev_day_levels.get("prev_close")
            if ph:
                ax_price.axhline(ph, color=C["prev_high"], linestyle=":", linewidth=1.0, alpha=0.7, zorder=1)
                ax_price.text(date_numbers[-1], ph, f" PDH {ph:.1f}", fontsize=7, color=C["prev_high"], va="bottom", zorder=5)
            if pl:
                ax_price.axhline(pl, color=C["prev_low"], linestyle=":", linewidth=1.0, alpha=0.7, zorder=1)
                ax_price.text(date_numbers[-1], pl, f" PDL {pl:.1f}", fontsize=7, color=C["prev_low"], va="top", zorder=5)
            if pc:
                ax_price.axhline(pc, color=C["prev_close"], linestyle=":", linewidth=1.0, alpha=0.7, zorder=1)
                ax_price.text(date_numbers[-1], pc, f" PDC {pc:.1f}", fontsize=7, color=C["prev_close"], va="bottom", zorder=5)

        # ── EMA 9/21 Overlay ──
        if "ema9" in plot_frame.columns and not plot_frame["ema9"].isna().all():
            ax_price.plot(date_numbers, plot_frame["ema9"], color=C["ema9"], linewidth=1.3, label="EMA9", zorder=4)
        if "ema21" in plot_frame.columns and not plot_frame["ema21"].isna().all():
            ax_price.plot(date_numbers, plot_frame["ema21"], color=C["ema21"], linewidth=1.3, label="EMA21", zorder=4)

        # ── Bollinger Bands ──
        if "bb_upper" in plot_frame.columns and not plot_frame["bb_upper"].isna().all():
            ax_price.plot(date_numbers, plot_frame["bb_upper"], color=C["bb_line"], linewidth=0.7, alpha=0.5, zorder=4)
            ax_price.plot(date_numbers, plot_frame["bb_lower"], color=C["bb_line"], linewidth=0.7, alpha=0.5, zorder=4)
            ax_price.fill_between(
                date_numbers, plot_frame["bb_upper"], plot_frame["bb_lower"],
                color=C["bb_fill"], alpha=0.06, zorder=0,
            )

        # ── VWAP ──
        if "vwap" in plot_frame.columns and not plot_frame["vwap"].isna().all():
            ax_price.plot(date_numbers, plot_frame["vwap"], color=C["vwap"], linewidth=2.0, label="VWAP", zorder=4)

        # ── Candlestick Pattern Annotations ──
        for pat in patterns:
            idx = pat["index"]
            if idx >= len(date_numbers):
                continue
            x = date_numbers[idx]
            price = pat["price"]
            color = C["pattern_bull"] if pat["bias"] == "bullish" else C["pattern_bear"]
            marker = "^" if pat["bias"] == "bullish" else "v"
            offset = float(plot_frame["atr"].iloc[idx]) * 0.5 if "atr" in plot_frame.columns else 1.0
            y = price - offset if pat["bias"] == "bullish" else price + offset

            ax_price.scatter(x, y, marker=marker, color=color, s=60, zorder=6, edgecolors="white", linewidths=0.3)
            ax_price.annotate(
                pat["pattern"], xy=(x, y),
                xytext=(0, -12 if pat["bias"] == "bullish" else 12),
                textcoords="offset points",
                fontsize=6, color=color, ha="center", va="top" if pat["bias"] == "bullish" else "bottom",
                zorder=6,
            )

        # ── RSI Panel ──
        if "rsi" in plot_frame.columns and not plot_frame["rsi"].isna().all():
            ax_rsi.plot(date_numbers, plot_frame["rsi"], color=C["rsi_line"], linewidth=1.4)
            ax_rsi.axhline(70, color=C["rsi_ob"], linestyle="--", linewidth=0.8, alpha=0.7)
            ax_rsi.axhline(30, color=C["rsi_os"], linestyle="--", linewidth=0.8, alpha=0.7)
            ax_rsi.axhline(50, color=C["rsi_mid"], linestyle=":", linewidth=0.6, alpha=0.5)
            ax_rsi.fill_between(date_numbers, plot_frame["rsi"], 70, where=(plot_frame["rsi"] >= 70), color=C["rsi_ob"], alpha=0.15)
            ax_rsi.fill_between(date_numbers, plot_frame["rsi"], 30, where=(plot_frame["rsi"] <= 30), color=C["rsi_os"], alpha=0.15)
            ax_rsi.set_ylim(0, 100)
            ax_rsi.set_ylabel("RSI", color=C["text_dim"], fontsize=9)

        # ── CVD Panel ──
        if "cvd" in plot_frame.columns and not plot_frame["cvd"].isna().all():
            ax_cvd.plot(date_numbers, plot_frame["cvd"], color=C["cvd_pos"], linewidth=1.4)
            ax_cvd.fill_between(
                date_numbers, plot_frame["cvd"], 0,
                where=(plot_frame["cvd"] >= 0), color=C["cvd_pos"], alpha=0.2, interpolate=True,
            )
            ax_cvd.fill_between(
                date_numbers, plot_frame["cvd"], 0,
                where=(plot_frame["cvd"] < 0), color=C["cvd_neg"], alpha=0.2, interpolate=True,
            )
            ax_cvd.axhline(0, color=C["spine"], linestyle="--", linewidth=0.8)

        # ── X-Axis: Full trading session ──
        market_day = pd.Timestamp(market_date).date()
        market_open_dt = pd.Timestamp(
            year=market_day.year, month=market_day.month, day=market_day.day,
            hour=self.market_open[0], minute=self.market_open[1],
        )
        market_close_dt = pd.Timestamp(
            year=market_day.year, month=market_day.month, day=market_day.day,
            hour=self.market_close[0], minute=self.market_close[1],
        )
        x_min = mdates.date2num(market_open_dt.to_pydatetime())
        x_max = mdates.date2num(market_close_dt.to_pydatetime())
        ax_price.set_xlim(x_min - candle_width, x_max + candle_width)

        # ── Legend ──
        ax_price.legend(
            loc="upper left", facecolor=C["bg"], edgecolor=C["spine"],
            labelcolor=C["text"], fontsize=8, framealpha=0.9,
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
            ax.grid(color=C["grid"], linestyle="--", linewidth=0.5, alpha=0.6)
            ax.tick_params(colors=C["text_dim"], labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(C["spine"])

        ax_cvd.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax_cvd.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))

        ax_price.set_ylabel("Price (\u20b9)", color=C["text_dim"], fontsize=9)
        ax_volume.set_ylabel("Vol", color=C["text_dim"], fontsize=9)
        ax_cvd.set_ylabel("CVD", color=C["text_dim"], fontsize=9)

        fig.autofmt_xdate()
        plt.tight_layout(rect=[0, 0, 1, 0.98])
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
