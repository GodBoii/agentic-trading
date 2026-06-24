from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.services.storage_service import StorageService


class NiftyDepthChartGenerator:
    """Build NIFTY market-structure charts from the recorder's NDJSON files."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.max_depth_packets = self._env_int("NIFTY_CHART_MAX_DEPTH_PACKETS", 700)
        self.max_full_packets = self._env_int("NIFTY_CHART_MAX_FULL_PACKETS", 1800)
        self.price_step = self._env_float("NIFTY_CHART_PRICE_STEP", 1.0)
        self.footprint_minutes = self._env_int("NIFTY_CHART_FOOTPRINT_MINUTES", 1)
        self.dom_levels = self._env_int("NIFTY_CHART_DOM_LEVELS", 48)

    def _env_int(self, key: str, default: int) -> int:
        try:
            return int(os.getenv(key, str(default)))
        except (TypeError, ValueError):
            return default

    def _env_float(self, key: str, default: float) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except (TypeError, ValueError):
            return default

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load_ndjson_tail(self, path: Path, max_rows: int) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if max_rows > 0 and len(rows) > max_rows:
            return rows[-max_rows:]
        return rows

    def _number(self, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(result) or math.isinf(result):
            return None
        return result

    def _packet_number(self, packet: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
        for key in keys:
            value = self._number(packet.get(key))
            if value is not None:
                return value
        return None

    def _parse_ts(self, value: Any) -> Optional[pd.Timestamp]:
        if not value:
            return None
        try:
            return pd.to_datetime(value, utc=True)
        except Exception:
            return None

    def _round_price(self, price: float) -> float:
        step = self.price_step if self.price_step > 0 else 1.0
        return round(round(price / step) * step, 2)

    def _extract_depth_levels(self, levels: Any, side: str) -> List[Dict[str, float]]:
        if not isinstance(levels, list):
            return []
        parsed: List[Dict[str, float]] = []
        for level in levels:
            if not isinstance(level, dict):
                continue
            price = self._packet_number(
                level,
                ("price", f"{side}_price", f"{side}Price", "bid_price", "ask_price"),
            )
            quantity = self._packet_number(
                level,
                (
                    "quantity",
                    "qty",
                    f"{side}_quantity",
                    f"{side}Quantity",
                    "bid_quantity",
                    "ask_quantity",
                    "bid_qty",
                    "ask_qty",
                ),
            )
            orders = self._packet_number(
                level,
                (
                    "orders",
                    "order_count",
                    "number_of_orders",
                    f"{side}_orders",
                    f"{side}Orders",
                    "bid_orders",
                    "ask_orders",
                ),
            )
            if price is None or quantity is None:
                continue
            parsed.append(
                {
                    "price": price,
                    "price_bin": self._round_price(price),
                    "quantity": quantity,
                    "orders": orders or 0.0,
                }
            )
        return parsed

    def _depth_dataframe(self, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        records: List[Dict[str, Any]] = []
        for row in rows:
            ts = self._parse_ts(row.get("captured_at_utc"))
            side = str(row.get("side") or "").lower()
            if ts is None or side not in {"bid", "ask"}:
                continue
            for level in self._extract_depth_levels(row.get("depth"), side):
                records.append(
                    {
                        "timestamp": ts,
                        "side": side,
                        "price": level["price"],
                        "price_bin": level["price_bin"],
                        "quantity": level["quantity"],
                        "orders": level["orders"],
                    }
                )
        if not records:
            return pd.DataFrame(columns=["timestamp", "side", "price", "price_bin", "quantity", "orders"])
        return pd.DataFrame.from_records(records).sort_values("timestamp")

    def _best_quotes_from_depth(self, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        records: List[Dict[str, Any]] = []
        for row in rows:
            ts = self._parse_ts(row.get("captured_at_utc"))
            side = str(row.get("side") or "").lower()
            levels = self._extract_depth_levels(row.get("depth"), side)
            if ts is None or side not in {"bid", "ask"} or not levels:
                continue
            if side == "bid":
                records.append({"timestamp": ts, "best_bid": max(level["price"] for level in levels)})
            else:
                records.append({"timestamp": ts, "best_ask": min(level["price"] for level in levels)})
        if not records:
            return pd.DataFrame(columns=["best_bid", "best_ask"])
        quotes = pd.DataFrame.from_records(records).set_index("timestamp").sort_index()
        return quotes.groupby(level=0).last().ffill().bfill()

    def _packet_best_quotes(self, packet: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        best_bid: Optional[float] = None
        best_ask: Optional[float] = None
        for level in packet.get("depth") or []:
            if not isinstance(level, dict):
                continue
            bid = self._number(level.get("bid_price"))
            ask = self._number(level.get("ask_price"))
            if bid is not None:
                best_bid = max(best_bid, bid) if best_bid is not None else bid
            if ask is not None:
                best_ask = min(best_ask, ask) if best_ask is not None else ask
        return best_bid, best_ask

    def _trade_dataframe(self, rows: List[Dict[str, Any]], depth_quotes: pd.DataFrame) -> pd.DataFrame:
        records: List[Dict[str, Any]] = []
        previous_volume: Optional[float] = None
        previous_ltp: Optional[float] = None

        for row in rows:
            ts = self._parse_ts(row.get("captured_at_utc"))
            packet = row.get("packet") if isinstance(row.get("packet"), dict) else {}
            if ts is None or not packet:
                continue

            ltp = self._packet_number(packet, ("LTP", "last_price", "lastPrice", "latest_traded_price"))
            volume = self._packet_number(packet, ("volume", "Volume", "total_volume"))
            ltq = self._packet_number(packet, ("LTQ", "last_traded_quantity", "lastTradedQuantity"))
            if ltp is None:
                continue

            quantity = 0.0
            if volume is not None:
                if previous_volume is not None and volume >= previous_volume:
                    quantity = volume - previous_volume
                previous_volume = volume
            if quantity <= 0 and ltq is not None:
                quantity = ltq
            if quantity <= 0:
                previous_ltp = ltp
                continue

            best_bid, best_ask = self._packet_best_quotes(packet)
            if (best_bid is None or best_ask is None) and not depth_quotes.empty:
                indexer = depth_quotes.index.get_indexer([ts], method="pad")
                if indexer.size and indexer[0] >= 0:
                    quote = depth_quotes.iloc[indexer[0]]
                    best_bid = self._number(quote.get("best_bid")) if best_bid is None else best_bid
                    best_ask = self._number(quote.get("best_ask")) if best_ask is None else best_ask

            aggressor = "neutral"
            method = "unknown"
            if best_ask is not None and ltp >= best_ask:
                aggressor = "buy"
                method = "ltp_at_or_above_ask"
            elif best_bid is not None and ltp <= best_bid:
                aggressor = "sell"
                method = "ltp_at_or_below_bid"
            elif previous_ltp is not None and ltp > previous_ltp:
                aggressor = "buy"
                method = "uptick_fallback"
            elif previous_ltp is not None and ltp < previous_ltp:
                aggressor = "sell"
                method = "downtick_fallback"

            records.append(
                {
                    "timestamp": ts,
                    "price": ltp,
                    "price_bin": self._round_price(ltp),
                    "quantity": quantity,
                    "volume": volume,
                    "ltq": ltq,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "aggressor": aggressor,
                    "classification_method": method,
                }
            )
            previous_ltp = ltp

        if not records:
            return pd.DataFrame(
                columns=[
                    "timestamp",
                    "price",
                    "price_bin",
                    "quantity",
                    "best_bid",
                    "best_ask",
                    "aggressor",
                    "classification_method",
                ]
            )
        return pd.DataFrame.from_records(records).sort_values("timestamp")

    def _trade_tick_dataframe(self, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        records: List[Dict[str, Any]] = []
        for row in rows:
            ts = self._parse_ts(row.get("captured_at_utc"))
            price = self._number(row.get("latest_price"))
            if ts is None or price is None:
                continue
            quantity = self._number(row.get("volume_delta"))
            if quantity is None or quantity <= 0:
                quantity = self._number(row.get("last_traded_quantity")) or 0.0
            if quantity <= 0:
                continue
            records.append(
                {
                    "timestamp": ts,
                    "price": price,
                    "price_bin": self._round_price(price),
                    "quantity": quantity,
                    "volume": self._number(row.get("volume")),
                    "ltq": self._number(row.get("last_traded_quantity")),
                    "best_bid": self._number(row.get("best_bid")),
                    "best_ask": self._number(row.get("best_ask")),
                    "aggressor": str(row.get("aggressor") or "neutral"),
                    "classification_method": str(row.get("classification_method") or "trade_ticks"),
                }
            )
        if not records:
            return pd.DataFrame(
                columns=[
                    "timestamp",
                    "price",
                    "price_bin",
                    "quantity",
                    "best_bid",
                    "best_ask",
                    "aggressor",
                    "classification_method",
                ]
            )
        return pd.DataFrame.from_records(records).sort_values("timestamp")

    def _chart_paths(self, market_date: str) -> Dict[str, Path]:
        output_dir = self.config.nifty_depth_charts_dir / market_date
        output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "output_dir": output_dir,
            "heatmap": output_dir / "nifty_bookmap_heatmap.png",
            "footprint": output_dir / "nifty_order_flow_footprint.png",
            "dom": output_dir / "nifty_dom_ladder.png",
            "summary": output_dir / "chart_summary.json",
        }

    def generate_for_market_date(self, market_date: str) -> Dict[str, Any]:
        data_dir = self.config.nifty_depth_data_dir / market_date
        paths = self._chart_paths(market_date)
        depth_rows = self._load_ndjson_tail(data_dir / "depth_200.ndjson", self.max_depth_packets)
        trade_tick_rows = self._load_ndjson_tail(data_dir / "trade_ticks.ndjson", self.max_full_packets)
        full_rows = self._load_ndjson_tail(data_dir / "full_market.ndjson", self.max_full_packets)

        depth_df = self._depth_dataframe(depth_rows)
        quote_df = self._best_quotes_from_depth(depth_rows)
        trade_tick_source = "trade_ticks.ndjson" if trade_tick_rows else "full_market.ndjson_fallback"
        trade_df = self._trade_tick_dataframe(trade_tick_rows) if trade_tick_rows else self._trade_dataframe(full_rows, quote_df)

        if depth_df.empty and trade_df.empty:
            payload = self._build_summary(market_date, paths, depth_df, trade_df, generated=False, trade_tick_source=trade_tick_source)
            StorageService.save_snapshot(paths["summary"], payload)
            StorageService.save_snapshot(self.config.nifty_depth_charts_latest_path, payload)
            return payload

        self._render_bookmap_heatmap(depth_df, quote_df, trade_df, paths["heatmap"], market_date)
        self._render_footprint_chart(trade_df, paths["footprint"], market_date)
        self._render_dom_ladder(depth_rows, trade_df, paths["dom"], market_date)

        payload = self._build_summary(market_date, paths, depth_df, trade_df, generated=True, trade_tick_source=trade_tick_source)
        StorageService.save_snapshot(paths["summary"], payload)
        StorageService.save_snapshot(self.config.nifty_depth_charts_latest_path, payload)
        return payload

    def _build_summary(
        self,
        market_date: str,
        paths: Dict[str, Path],
        depth_df: pd.DataFrame,
        trade_df: pd.DataFrame,
        *,
        generated: bool,
        trade_tick_source: str,
    ) -> Dict[str, Any]:
        buy_volume = 0.0
        sell_volume = 0.0
        neutral_volume = 0.0
        if not trade_df.empty:
            buy_volume = float(trade_df.loc[trade_df["aggressor"] == "buy", "quantity"].sum())
            sell_volume = float(trade_df.loc[trade_df["aggressor"] == "sell", "quantity"].sum())
            neutral_volume = float(trade_df.loc[trade_df["aggressor"] == "neutral", "quantity"].sum())

        heavy_bid_levels: List[Dict[str, Any]] = []
        heavy_ask_levels: List[Dict[str, Any]] = []
        if not depth_df.empty:
            grouped = (
                depth_df.groupby(["side", "price_bin"], as_index=False)["quantity"]
                .mean()
                .sort_values("quantity", ascending=False)
            )
            heavy_bid_levels = grouped[grouped["side"] == "bid"].head(8).to_dict("records")
            heavy_ask_levels = grouped[grouped["side"] == "ask"].head(8).to_dict("records")

        charts = {
            "bookmap_heatmap": {
                "path": str(paths["heatmap"]),
                "description": "Liquidity heatmap with resting depth intensity, best bid/ask traces, and trade bubbles.",
            },
            "order_flow_footprint": {
                "path": str(paths["footprint"]),
                "description": "Footprint-style candle chart built from sampled full-market packets and inferred aggressor side.",
            },
            "dom_ladder": {
                "path": str(paths["dom"]),
                "description": "Latest 200-depth DOM ladder with bid and ask resting quantity bars.",
            },
        }
        chart_paths_ordered = [info["path"] for info in charts.values()]
        return {
            "stage": "nifty_market_depth_charting",
            "generated": generated,
            "generated_at_utc": self._now_utc(),
            "market_date": market_date,
            "input": {
                "depth_rows_used": len(depth_df),
                "trade_rows_used": len(trade_df),
                "trade_tick_source": trade_tick_source,
                "max_depth_packets": self.max_depth_packets,
                "max_full_packets": self.max_full_packets,
                "price_step": self.price_step,
                "footprint_minutes": self.footprint_minutes,
            },
            "charts": charts,
            "chart_count": len(charts) if generated else 0,
            "chart_paths_ordered": chart_paths_ordered if generated else [],
            "order_flow_summary": {
                "buy_volume": round(buy_volume, 3),
                "sell_volume": round(sell_volume, 3),
                "neutral_volume": round(neutral_volume, 3),
                "delta": round(buy_volume - sell_volume, 3),
                "total_classified_volume": round(buy_volume + sell_volume + neutral_volume, 3),
            },
            "liquidity_summary": {
                "heavy_bid_levels_by_average_quantity": heavy_bid_levels,
                "heavy_ask_levels_by_average_quantity": heavy_ask_levels,
            },
            "limitations": [
                "Depth is real 200-level resting liquidity captured by our recorder.",
                "Footprint aggressor side is inferred from sampled full-market packets plus best bid/ask or tick direction.",
                "For exchange-grade footprint accuracy, reduce raw write throttling and persist every trade tick with matching bid/ask.",
            ],
        }

    def _price_ylim(self, depth_df: pd.DataFrame, trade_df: pd.DataFrame) -> Optional[Tuple[float, float]]:
        prices: List[float] = []
        if not trade_df.empty:
            low = float(trade_df["price"].quantile(0.02))
            high = float(trade_df["price"].quantile(0.98))
            prices.extend([low, high])
        if not depth_df.empty:
            low = float(depth_df["price"].quantile(0.04))
            high = float(depth_df["price"].quantile(0.96))
            prices.extend([low, high])
        if not prices:
            return None
        low = min(prices)
        high = max(prices)
        if low == high:
            low -= 5
            high += 5
        margin = max((high - low) * 0.08, self.price_step * 4)
        return low - margin, high + margin

    def _render_bookmap_heatmap(
        self,
        depth_df: pd.DataFrame,
        quote_df: pd.DataFrame,
        trade_df: pd.DataFrame,
        output_path: Path,
        market_date: str,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(19, 10))
        fig.patch.set_facecolor("#0f1b20")
        ax.set_facecolor("#0f1b20")

        if not depth_df.empty:
            limit = max(float(depth_df["quantity"].quantile(0.98)), 1.0)
            bids = depth_df[depth_df["side"] == "bid"]
            asks = depth_df[depth_df["side"] == "ask"]
            if not bids.empty:
                ax.scatter(
                    bids["timestamp"],
                    bids["price"],
                    c=bids["quantity"].clip(upper=limit),
                    cmap="winter",
                    s=18,
                    marker="s",
                    alpha=0.42,
                    edgecolors="none",
                    zorder=1,
                )
            if not asks.empty:
                ask_scatter = ax.scatter(
                    asks["timestamp"],
                    asks["price"],
                    c=asks["quantity"].clip(upper=limit),
                    cmap="hot",
                    s=18,
                    marker="s",
                    alpha=0.42,
                    edgecolors="none",
                    zorder=1,
                )
                cbar = fig.colorbar(ask_scatter, ax=ax, pad=0.01, shrink=0.75)
                cbar.set_label("Resting quantity intensity")

        if not quote_df.empty:
            ax.plot(quote_df.index, quote_df["best_bid"], color="#39d98a", linewidth=1.0, label="Best bid", zorder=3)
            ax.plot(quote_df.index, quote_df["best_ask"], color="#ff5d57", linewidth=1.0, label="Best ask", zorder=3)

        if not trade_df.empty:
            color_map = {"buy": "#00e676", "sell": "#ff3b30", "neutral": "#ffd54f"}
            max_qty = max(float(trade_df["quantity"].quantile(0.95)), 1.0)
            sizes = 30 + (trade_df["quantity"].clip(upper=max_qty) / max_qty) * 650
            ax.scatter(
                trade_df["timestamp"],
                trade_df["price"],
                s=sizes,
                c=[color_map.get(side, "#ffd54f") for side in trade_df["aggressor"]],
                alpha=0.78,
                edgecolors="#d8eef2",
                linewidth=0.35,
                zorder=5,
                label="Trade volume bubbles",
            )

        ylim = self._price_ylim(depth_df, trade_df)
        if ylim:
            ax.set_ylim(*ylim)
        ax.set_title(f"NIFTY 200-Depth Liquidity Heatmap + Trade Bubbles ({market_date})", fontsize=16)
        ax.set_xlabel("Time")
        ax.set_ylabel("NIFTY future price")
        ax.grid(True, color="#44616a", linestyle=":", alpha=0.35)
        ax.legend(loc="upper left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        fig.savefig(output_path, dpi=170, bbox_inches="tight")
        plt.close(fig)

    def _render_footprint_chart(self, trade_df: pd.DataFrame, output_path: Path, market_date: str) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        fig, ax = plt.subplots(figsize=(19, 10))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        if trade_df.empty:
            ax.text(0.5, 0.5, "No full-market trade samples available", ha="center", va="center", fontsize=18)
            ax.axis("off")
            fig.savefig(output_path, dpi=170, bbox_inches="tight")
            plt.close(fig)
            return

        freq = f"{max(self.footprint_minutes, 1)}min"
        df = trade_df.copy()
        df["bucket"] = df["timestamp"].dt.floor(freq)
        buckets = list(df["bucket"].drop_duplicates().sort_values())
        if len(buckets) > 42:
            buckets = buckets[-42:]
            df = df[df["bucket"].isin(buckets)]

        footprint: Dict[Tuple[pd.Timestamp, float], Dict[str, float]] = defaultdict(lambda: {"buy": 0.0, "sell": 0.0, "neutral": 0.0})
        for row in df.itertuples(index=False):
            footprint[(row.bucket, row.price_bin)][row.aggressor] += float(row.quantity)

        prices = sorted(df["price_bin"].dropna().unique())
        if not prices:
            prices = [self._round_price(float(df["price"].iloc[-1]))]
        price_to_y = {price: idx for idx, price in enumerate(prices)}
        max_cell_volume = max((sum(sides.values()) for sides in footprint.values()), default=1.0)
        max_cell_volume = max(max_cell_volume, 1.0)

        candle_ohlc = df.groupby("bucket").agg(open=("price", "first"), high=("price", "max"), low=("price", "min"), close=("price", "last"))
        for x, bucket in enumerate(buckets):
            if bucket not in candle_ohlc.index:
                continue
            row = candle_ohlc.loc[bucket]
            open_y = price_to_y.get(self._round_price(float(row["open"])), 0)
            close_y = price_to_y.get(self._round_price(float(row["close"])), open_y)
            high_y = price_to_y.get(self._round_price(float(row["high"])), max(open_y, close_y))
            low_y = price_to_y.get(self._round_price(float(row["low"])), min(open_y, close_y))
            color = "#137a2f" if row["close"] >= row["open"] else "#c72535"
            ax.vlines(x, low_y - 0.4, high_y + 0.4, color=color, linewidth=2.2, zorder=2)
            body_low = min(open_y, close_y) - 0.35
            body_height = max(abs(close_y - open_y), 0.45)
            ax.add_patch(Rectangle((x - 0.08, body_low), 0.16, body_height, facecolor=color, edgecolor=color, alpha=0.95, zorder=3))

        for x, bucket in enumerate(buckets):
            for price in prices:
                sides = footprint.get((bucket, price))
                if not sides:
                    continue
                y = price_to_y[price]
                sell = sides.get("sell", 0.0)
                buy = sides.get("buy", 0.0)
                neutral = sides.get("neutral", 0.0)
                total = sell + buy + neutral
                intensity = min(total / max_cell_volume, 1.0)
                if sell > 0:
                    ax.add_patch(Rectangle((x - 0.47, y - 0.42), 0.38, 0.84, facecolor="#ff9aa2", edgecolor="none", alpha=0.22 + 0.62 * intensity))
                if buy > 0:
                    ax.add_patch(Rectangle((x + 0.09, y - 0.42), 0.38, 0.84, facecolor="#9be7a1", edgecolor="none", alpha=0.22 + 0.62 * intensity))
                text = f"{int(round(sell))} x {int(round(buy))}"
                if neutral:
                    text = f"{text}\nN {int(round(neutral))}"
                ax.text(x, y, text, ha="center", va="center", fontsize=7, color="#111111", zorder=4)

        deltas: List[float] = []
        volumes: List[float] = []
        for bucket in buckets:
            bucket_rows = df[df["bucket"] == bucket]
            buy = float(bucket_rows.loc[bucket_rows["aggressor"] == "buy", "quantity"].sum())
            sell = float(bucket_rows.loc[bucket_rows["aggressor"] == "sell", "quantity"].sum())
            neutral = float(bucket_rows.loc[bucket_rows["aggressor"] == "neutral", "quantity"].sum())
            deltas.append(buy - sell)
            volumes.append(buy + sell + neutral)

        summary_base = -4.0
        cumulative = 0.0
        for x, (delta, volume) in enumerate(zip(deltas, volumes)):
            cumulative += delta
            delta_color = "#94d38c" if delta >= 0 else "#ff8a8a"
            ax.add_patch(Rectangle((x - 0.48, summary_base), 0.96, 0.75, facecolor=delta_color, edgecolor="#888888", linewidth=0.4))
            ax.text(x, summary_base + 0.38, f"D {int(delta)}", ha="center", va="center", fontsize=7)
            ax.text(x, summary_base - 0.42, f"V {int(volume)}", ha="center", va="center", fontsize=7, color="#333333")
            ax.text(x, summary_base - 1.12, f"C {int(cumulative)}", ha="center", va="center", fontsize=7, color="#333333")

        ax.set_xlim(-0.75, max(len(buckets) - 0.25, 1))
        ax.set_ylim(summary_base - 1.75, len(prices) + 0.6)
        ax.set_xticks(range(len(buckets)))
        ax.set_xticklabels([pd.Timestamp(bucket).strftime("%H:%M") for bucket in buckets], rotation=0, fontsize=8)
        tick_step = max(1, len(prices) // 24)
        ax.set_yticks(range(0, len(prices), tick_step))
        ax.set_yticklabels([f"{prices[idx]:.2f}" for idx in range(0, len(prices), tick_step)], fontsize=8)
        ax.grid(True, color="#e7e7e7", linewidth=0.5)
        ax.set_title(f"NIFTY Order-Flow Footprint Approximation ({self.footprint_minutes}m, {market_date})", fontsize=15)
        ax.set_xlabel("Candle time")
        ax.set_ylabel("Price bin")
        fig.savefig(output_path, dpi=170, bbox_inches="tight")
        plt.close(fig)

    def _last_sides(self, depth_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
        bid_levels: List[Dict[str, float]] = []
        ask_levels: List[Dict[str, float]] = []
        for row in reversed(depth_rows):
            side = str(row.get("side") or "").lower()
            if side == "bid" and not bid_levels:
                bid_levels = self._extract_depth_levels(row.get("depth"), "bid")
            elif side == "ask" and not ask_levels:
                ask_levels = self._extract_depth_levels(row.get("depth"), "ask")
            if bid_levels and ask_levels:
                break
        return bid_levels, ask_levels

    def _render_dom_ladder(
        self,
        depth_rows: List[Dict[str, Any]],
        trade_df: pd.DataFrame,
        output_path: Path,
        market_date: str,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        bid_levels, ask_levels = self._last_sides(depth_rows)
        fig, ax = plt.subplots(figsize=(9, 14))
        fig.patch.set_facecolor("#111c24")
        ax.set_facecolor("#111c24")

        if not bid_levels and not ask_levels:
            ax.text(0.5, 0.5, "No depth ladder available", ha="center", va="center", color="white", fontsize=16)
            ax.axis("off")
            fig.savefig(output_path, dpi=170, bbox_inches="tight")
            plt.close(fig)
            return

        best_bid = max((level["price"] for level in bid_levels), default=None)
        best_ask = min((level["price"] for level in ask_levels), default=None)
        last_price = float(trade_df["price"].iloc[-1]) if not trade_df.empty else None

        selected_bids = sorted(bid_levels, key=lambda item: item["price"], reverse=True)[: self.dom_levels // 2]
        selected_asks = sorted(ask_levels, key=lambda item: item["price"])[: self.dom_levels // 2]
        prices = sorted({level["price"] for level in selected_bids + selected_asks}, reverse=True)
        price_to_y = {price: idx for idx, price in enumerate(prices)}
        max_qty = max((level["quantity"] for level in selected_bids + selected_asks), default=1.0)

        ax.axvline(0, color="#dde8ef", linewidth=1.0)
        for level in selected_asks:
            y = price_to_y[level["price"]]
            width = 0.95 * (level["quantity"] / max_qty)
            ax.barh(y, width, left=0.18, height=0.75, color="#d8202a", alpha=0.85)
            ax.text(0.21, y, f"{int(level['quantity'])}", va="center", ha="left", color="white", fontsize=9)
        for level in selected_bids:
            y = price_to_y[level["price"]]
            width = 0.95 * (level["quantity"] / max_qty)
            ax.barh(y, -width, left=-0.18, height=0.75, color="#176fc6", alpha=0.88)
            ax.text(-0.21, y, f"{int(level['quantity'])}", va="center", ha="right", color="white", fontsize=9)

        for price, y in price_to_y.items():
            ax.text(0, y, f"{price:.2f}", va="center", ha="center", color="#f5f7fa", fontsize=9, bbox={"facecolor": "#1d2b35", "edgecolor": "#394b56", "pad": 1.5})

        if last_price is not None:
            nearest = min(prices, key=lambda price: abs(price - last_price))
            ax.axhline(price_to_y[nearest], color="#ffd166", linewidth=2.0, alpha=0.8)
            ax.text(1.12, price_to_y[nearest], f"LTP {last_price:.2f}", va="center", ha="left", color="#ffd166", fontsize=9)

        title_bits = [f"NIFTY DOM Ladder ({market_date})"]
        if best_bid is not None and best_ask is not None:
            title_bits.append(f"spread {best_ask - best_bid:.2f}")
        ax.set_title(" - ".join(title_bits), color="white", fontsize=14, pad=16)
        ax.text(-0.55, -1.0, "Bids", color="#69b7ff", fontsize=12, ha="center")
        ax.text(0.55, -1.0, "Asks", color="#ff7373", fontsize=12, ha="center")
        ax.set_xlim(-1.35, 1.35)
        ax.set_ylim(len(prices) - 0.25, -1.4)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        fig.savefig(output_path, dpi=170, bbox_inches="tight")
        plt.close(fig)
