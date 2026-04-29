from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CandlestickChartService:
    def __init__(self, market_timezone: str):
        self.market_timezone = market_timezone
        self.resolved_timezone = self._resolve_timezone(market_timezone)

    def build_intraday_chart_set(
        self,
        frame: pd.DataFrame,
        display_name: str,
        market_date: str,
        output_dir: Path,
    ) -> Dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        local_frame = self._to_market_frame(frame)
        today_frame = self._today_frame(local_frame, market_date)
        if today_frame.empty:
            raise ValueError("No intraday candles available for the requested market date.")

        charts: Dict[str, Any] = {}
        for timeframe in [5, 15]:
            resampled = self._resample_frame(today_frame, timeframe)
            filename = f"{self._slugify(display_name)}-{market_date}-{timeframe}m.png"
            path = output_dir / filename
            self._render_chart(
                frame=resampled,
                title=f"{display_name} {timeframe}m",
                output_path=path,
            )
            charts[f"{timeframe}m"] = {
                "timeframe_minutes": timeframe,
                "path": str(path),
                "candles": int(len(resampled)),
            }

        return {
            "market_date": market_date,
            "chart_count": len(charts),
            "charts": charts,
        }

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

    def _today_frame(self, frame: pd.DataFrame, market_date: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        market_day = pd.Timestamp(market_date).date()
        filtered = frame[frame["timestamp"].dt.date == market_day].copy()
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
        
        # Fill missing ATR values for initial rows (or backward fill if needed)
        ohlcv['atr'] = ohlcv['atr'].bfill()
        
        return ohlcv.tail(80)

    def _render_chart(self, frame: pd.DataFrame, title: str, output_path: Path) -> None:
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

        # Make the index timezone-naive so matplotlib plots the local time exactly as-is
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
            # Fill area for CVD
            ax_cvd.fill_between(
                date_numbers, 
                plot_frame["cvd"], 
                0, 
                where=(plot_frame["cvd"] >= 0), 
                color="#3b82f6", 
                alpha=0.3,
                interpolate=True
            )
            ax_cvd.fill_between(
                date_numbers, 
                plot_frame["cvd"], 
                0, 
                where=(plot_frame["cvd"] < 0), 
                color="#ef4444", 
                alpha=0.3,
                interpolate=True
            )
            ax_cvd.axhline(0, color="#4a4a4a", linestyle="--", linewidth=1)

        # Enhance Title with ATR, VWAP, and Currency Data
        latest_vwap = plot_frame["vwap"].iloc[-1] if "vwap" in plot_frame.columns and not plot_frame["vwap"].isna().all() else 0.0
        latest_atr = plot_frame["atr"].iloc[-1] if "atr" in plot_frame.columns and not plot_frame["atr"].isna().all() else 0.0
        
        full_title = f"{title} | VWAP: Rs. {latest_vwap:.2f} | ATR(14): Rs. {latest_atr:.2f} | Note: Indian Currency (Rs., Crores)"
        ax_price.set_title(full_title, color="#f8f4e9", fontsize=16, pad=12)
        
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
        
        ax_volume.set_ylabel("Vol", color="#d4d4d4")
        ax_price.set_ylabel("Price (Rs.)", color="#d4d4d4")
        ax_cvd.set_ylabel("CVD", color="#d4d4d4")
        
        # Ensure x-axis correctly scales to data
        ax_price.set_xlim([date_numbers[0] - candle_width, date_numbers[-1] + candle_width])
        
        fig.autofmt_xdate()
        plt.tight_layout()
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
