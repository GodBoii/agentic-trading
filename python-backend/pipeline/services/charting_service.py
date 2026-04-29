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

    def _resample_frame(self, frame: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
        rule = f"{timeframe_minutes}min"
        ohlcv = (
            frame[["open", "high", "low", "close", "volume"]]
            .resample(rule, label="right", closed="right")
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
        return ohlcv.tail(80)

    def _render_chart(self, frame: pd.DataFrame, title: str, output_path: Path) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        if frame.empty:
            raise ValueError(f"Cannot render empty chart for {title}.")

        fig, (ax_price, ax_volume) = plt.subplots(
            2,
            1,
            figsize=(12, 8),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1]},
        )
        fig.patch.set_facecolor("#0b0b0b")
        ax_price.set_facecolor("#0b0b0b")
        ax_volume.set_facecolor("#0b0b0b")

        date_numbers = mdates.date2num(frame.index.to_pydatetime())
        candle_width = self._candle_width(date_numbers)

        for index, (_, row) in enumerate(frame.iterrows()):
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

        ax_price.set_title(title, color="#f8f4e9", fontsize=16, pad=12)
        ax_price.grid(color="#2a2a2a", linestyle="--", linewidth=0.6, alpha=0.8)
        ax_volume.grid(color="#2a2a2a", linestyle="--", linewidth=0.4, alpha=0.6)
        ax_price.tick_params(colors="#d4d4d4")
        ax_volume.tick_params(colors="#d4d4d4")
        ax_price.spines[:].set_color("#4a4a4a")
        ax_volume.spines[:].set_color("#4a4a4a")
        ax_volume.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax_volume.set_ylabel("Vol", color="#d4d4d4")
        ax_price.set_ylabel("Price", color="#d4d4d4")
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
