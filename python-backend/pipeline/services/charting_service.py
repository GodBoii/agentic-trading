from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CandlestickChartService:
    """Generates candlestick chart images with full trading-day x-axis (9:15-15:30).

    Charts always show the complete market session on the x-axis regardless of how
    much data is available. If current time is 12:00, candles end in the middle with
    empty space to the right — exactly like TradingView.
    """

    # Timeframes for current day charts
    CURRENT_DAY_TIMEFRAMES: List[int] = [1, 5, 15, 30, 60]
    # Timeframes for previous day charts
    PREVIOUS_DAY_TIMEFRAMES: List[int] = [5, 15, 60]

    def __init__(self, market_timezone: str, market_open: Tuple[int, int] = (9, 15), market_close: Tuple[int, int] = (15, 30)):
        self.market_timezone = market_timezone
        self.resolved_timezone = self._resolve_timezone(market_timezone)
        self.market_open = market_open  # (hour, minute)
        self.market_close = market_close  # (hour, minute)

    def build_intraday_chart_set(
        self,
        frame: pd.DataFrame,
        display_name: str,
        market_date: str,
        output_dir: Path,
    ) -> Dict[str, Any]:
        """Build the full chart set: current day + previous trading day charts.

        Returns a dict with chart metadata for all generated images.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        local_frame = self._to_market_frame(frame)

        # --- Current day charts ---
        today_frame = self._day_frame(local_frame, market_date)
        if today_frame.empty:
            raise ValueError("No intraday candles available for the requested market date.")

        charts: Dict[str, Any] = {}
        chart_paths_ordered: List[str] = []

        for timeframe in self.CURRENT_DAY_TIMEFRAMES:
            resampled = self._resample_frame(today_frame, timeframe)
            tf_label = self._timeframe_label(timeframe)
            filename = f"{self._slugify(display_name)}-{market_date}-current-{tf_label}.png"
            path = output_dir / filename
            self._render_chart(
                frame=resampled,
                title=f"{display_name} {tf_label}",
                subtitle=f"CURRENT DAY — {market_date}",
                output_path=path,
                market_date=market_date,
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

        # --- Previous trading day charts ---
        prev_date = self._previous_trading_day(market_date)
        prev_date_str = prev_date.isoformat()
        prev_frame = self._day_frame(local_frame, prev_date_str)

        if not prev_frame.empty:
            for timeframe in self.PREVIOUS_DAY_TIMEFRAMES:
                resampled = self._resample_frame(prev_frame, timeframe)
                tf_label = self._timeframe_label(timeframe)
                filename = f"{self._slugify(display_name)}-{prev_date_str}-previous-{tf_label}.png"
                path = output_dir / filename
                self._render_chart(
                    frame=resampled,
                    title=f"{display_name} {tf_label}",
                    subtitle=f"PREVIOUS DAY — {prev_date_str}",
                    output_path=path,
                    market_date=prev_date_str,
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
        }

    def _previous_trading_day(self, market_date_str: str) -> date:
        """Get the previous trading day, skipping weekends (Sat=5, Sun=6)."""
        current = date.fromisoformat(market_date_str)
        prev = current - timedelta(days=1)
        # Skip weekends
        while prev.weekday() >= 5:  # Saturday=5, Sunday=6
            prev -= timedelta(days=1)
        return prev

    def _timeframe_label(self, minutes: int) -> str:
        """Human-readable timeframe label."""
        if minutes >= 60:
            hours = minutes // 60
            return f"{hours}h"
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
        """Extract a single day's data from the multi-day frame."""
        if frame.empty:
            return frame
        market_day = pd.Timestamp(market_date_str).date()
        filtered = frame[frame["timestamp"].dt.date == market_day].copy()
        if filtered.empty:
            return filtered
        return filtered.set_index("timestamp")

    def _add_base_indicators(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        df = frame.copy()

        # VWAP
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['vp'] = df['typical_price'] * df['volume']
        df['cum_vp'] = df['vp'].cumsum()
        df['cum_vol'] = df['volume'].cumsum()
        df['vwap'] = df['cum_vp'] / df['cum_vol']

        # Estimated CVD (Cumulative Volume Delta)
        df['delta'] = df['volume']
        df.loc[df['close'] < df['open'], 'delta'] = -df['volume']
        df['cvd'] = df['delta'].cumsum()

        return df

    def _resample_frame(self, frame: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
        rule = f"{timeframe_minutes}min"

        df = self._add_base_indicators(frame)

        ohlcv = (
            df[["open", "high", "low", "close", "volume", "vwap", "cvd"]]
            .resample(rule, label="left", closed="left")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "vwap": "last",
                    "cvd": "last",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
        )

        # Calculate ATR (14 period) on resampled data
        high_low = ohlcv['high'] - ohlcv['low']
        high_close_prev = (ohlcv['high'] - ohlcv['close'].shift(1)).abs()
        low_close_prev = (ohlcv['low'] - ohlcv['close'].shift(1)).abs()
        true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        ohlcv['atr'] = true_range.rolling(window=14).mean()
        ohlcv['atr'] = ohlcv['atr'].bfill()

        return ohlcv

    def _render_chart(
        self,
        frame: pd.DataFrame,
        title: str,
        subtitle: str,
        output_path: Path,
        market_date: str,
    ) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        if frame.empty:
            raise ValueError(f"Cannot render empty chart for {title}.")

        fig, (ax_price, ax_volume, ax_cvd) = plt.subplots(
            3,
            1,
            figsize=(12, 10),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1, 1]},
        )
        fig.patch.set_facecolor("#0b0b0b")
        ax_price.set_facecolor("#0b0b0b")
        ax_volume.set_facecolor("#0b0b0b")
        ax_cvd.set_facecolor("#0b0b0b")

        # Make the index timezone-naive so matplotlib plots the local time as-is
        plot_frame = frame.copy()
        if plot_frame.index.tz is not None:
            plot_frame.index = plot_frame.index.tz_localize(None)

        date_numbers = mdates.date2num(plot_frame.index.to_pydatetime())
        candle_width = self._candle_width(date_numbers)

        for index, (_, row) in enumerate(plot_frame.iterrows()):
            x = date_numbers[index]
            open_price = float(row["open"])
            close_price = float(row["close"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            volume = float(row["volume"])
            is_up = close_price >= open_price
            color = "#22c55e" if is_up else "#ef4444"

            ax_price.vlines(x, low_price, high_price, color=color, linewidth=1.2)
            body_low = min(open_price, close_price)
            body_height = max(abs(close_price - open_price), 0.01)
            ax_price.add_patch(
                Rectangle(
                    (x - candle_width / 2, body_low),
                    candle_width,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=1.0,
                )
            )
            ax_volume.bar(x, volume, width=candle_width, color=color, alpha=0.8)

        # Plot VWAP Overlay
        if "vwap" in plot_frame.columns and not plot_frame["vwap"].isna().all():
            ax_price.plot(date_numbers, plot_frame["vwap"], color="#f59e0b", linewidth=1.8, label="VWAP")
            ax_price.legend(loc="upper left", facecolor="#0b0b0b", edgecolor="#4a4a4a", labelcolor="#d4d4d4")

        # Plot CVD
        if "cvd" in plot_frame.columns and not plot_frame["cvd"].isna().all():
            ax_cvd.plot(date_numbers, plot_frame["cvd"], color="#3b82f6", linewidth=1.5)
            ax_cvd.fill_between(
                date_numbers,
                plot_frame["cvd"],
                0,
                where=(plot_frame["cvd"] >= 0),
                color="#3b82f6",
                alpha=0.3,
                interpolate=True,
            )
            ax_cvd.fill_between(
                date_numbers,
                plot_frame["cvd"],
                0,
                where=(plot_frame["cvd"] < 0),
                color="#ef4444",
                alpha=0.3,
                interpolate=True,
            )
            ax_cvd.axhline(0, color="#4a4a4a", linestyle="--", linewidth=1)

        # --- FIXED X-AXIS: Always show full trading session 9:15 - 15:30 ---
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

        # Enhanced title with VWAP, ATR and currency info
        latest_vwap = plot_frame["vwap"].iloc[-1] if "vwap" in plot_frame.columns and not plot_frame["vwap"].isna().all() else 0.0
        latest_atr = plot_frame["atr"].iloc[-1] if "atr" in plot_frame.columns and not plot_frame["atr"].isna().all() else 0.0

        full_title = f"{title} | VWAP: Rs. {latest_vwap:.2f} | ATR(14): Rs. {latest_atr:.2f} | Note: Indian Currency (Rs., Crores)"
        ax_price.set_title(full_title, color="#f8f4e9", fontsize=14, pad=12)

        # Subtitle clearly indicating Current Day / Previous Day + date
        fig.suptitle(subtitle, color="#82aaff", fontsize=11, fontweight="bold", y=0.98)

        ax_price.grid(color="#2a2a2a", linestyle="--", linewidth=0.6, alpha=0.8)
        ax_volume.grid(color="#2a2a2a", linestyle="--", linewidth=0.4, alpha=0.6)
        ax_cvd.grid(color="#2a2a2a", linestyle="--", linewidth=0.4, alpha=0.6)

        ax_price.tick_params(colors="#d4d4d4")
        ax_volume.tick_params(colors="#d4d4d4")
        ax_cvd.tick_params(colors="#d4d4d4")

        ax_price.spines[:].set_color("#4a4a4a")
        ax_volume.spines[:].set_color("#4a4a4a")
        ax_cvd.spines[:].set_color("#4a4a4a")

        ax_cvd.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        # Set major ticks every 30 minutes for clean labeling
        ax_cvd.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))

        ax_volume.set_ylabel("Vol", color="#d4d4d4")
        ax_price.set_ylabel("Price (Rs.)", color="#d4d4d4")
        ax_cvd.set_ylabel("CVD", color="#d4d4d4")

        fig.autofmt_xdate()
        plt.tight_layout(rect=[0, 0, 1, 0.97])  # Leave room for suptitle
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    def _candle_width(self, date_numbers: Any) -> float:
        if len(date_numbers) < 2:
            return 0.003
        diffs = [abs(date_numbers[idx] - date_numbers[idx - 1]) for idx in range(1, len(date_numbers))]
        median = sorted(diffs)[len(diffs) // 2] if diffs else 0.003
        return max(median * 0.7, 0.0015)

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
