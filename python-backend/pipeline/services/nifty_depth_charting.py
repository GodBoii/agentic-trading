from __future__ import annotations

import json
import math
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.services.charting_service import CandlestickChartService
from pipeline.services.market_reference_service import MarketReferenceService
from pipeline.services.storage_service import StorageService


class NiftyDepthChartGenerator:
    """Build NIFTY market-structure charts from the recorder's NDJSON files."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.max_depth_packets = self._env_int("NIFTY_CHART_MAX_DEPTH_PACKETS", 700)
        self.max_full_packets = self._env_int("NIFTY_CHART_MAX_FULL_PACKETS", 1800)
        self.price_step = self._env_float("NIFTY_CHART_PRICE_STEP", 1.0)
        self.footprint_minutes = self._env_int("NIFTY_CHART_FOOTPRINT_MINUTES", 1)
        self.max_footprint_buckets = self._env_int("NIFTY_CHART_MAX_FOOTPRINT_BUCKETS", 42)
        self.dom_levels = self._env_int("NIFTY_CHART_DOM_LEVELS", 48)
        self.sample_mode = os.getenv("NIFTY_CHART_SAMPLE_MODE", "tail").strip().lower()
        self.cvd_max_rows = self._env_int("NIFTY_CHART_MAX_CVD_ROWS", 5000)
        self.option_chain_strikes_each_side = self._env_int("NIFTY_OPTION_CHAIN_CHART_STRIKES_EACH_SIDE", 5)
        self.reference = MarketReferenceService(config)

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

    def _parse_ndjson_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not line.strip():
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _load_ndjson_tail(self, path: Path, max_rows: int) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        if max_rows <= 0:
            rows: List[Dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    row = self._parse_ndjson_line(line)
                    if row is not None:
                        rows.append(row)
            return rows

        tail: deque[Dict[str, Any]] = deque(maxlen=max_rows)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = self._parse_ndjson_line(line)
                if row is not None:
                    tail.append(row)
        return list(tail)

    def _count_ndjson_rows(self, path: Path) -> int:
        count = 0
        if not path.exists():
            return count
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    count += 1
        return count

    def _load_ndjson_span_sample(self, path: Path, max_rows: int) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        if max_rows <= 0:
            return self._load_ndjson_tail(path, max_rows)

        row_count = self._count_ndjson_rows(path)
        if row_count <= max_rows:
            return self._load_ndjson_tail(path, max_rows)

        if max_rows == 1:
            target_indexes = {row_count - 1}
        else:
            target_indexes = {
                round(index * (row_count - 1) / (max_rows - 1))
                for index in range(max_rows)
            }

        rows: List[Dict[str, Any]] = []
        current_index = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if current_index in target_indexes:
                    row = self._parse_ndjson_line(line)
                    if row is not None:
                        rows.append(row)
                current_index += 1
        return rows

    def _load_ndjson(self, path: Path, max_rows: int) -> List[Dict[str, Any]]:
        if self.sample_mode in {"span", "full_day", "full-session", "full_session"}:
            return self._load_ndjson_span_sample(path, max_rows)
        return self._load_ndjson_tail(path, max_rows)

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

    def _coerce_int(self, value: Any) -> Optional[int]:
        number = self._number(value)
        return int(number) if number is not None else None

    def _parse_iso_date(self, value: Any) -> Optional[pd.Timestamp]:
        if not value:
            return None
        try:
            return pd.Timestamp(value).normalize()
        except Exception:
            return None

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

    def _cvd_dataframe(self, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        records: List[Dict[str, Any]] = []
        for row in rows:
            ts = self._parse_ts(row.get("captured_at_utc") or row.get("timestamp_ist"))
            price = self._number(row.get("latest_price") or row.get("ltp"))
            cvd = self._number(row.get("cvd"))
            if ts is None or cvd is None:
                continue
            records.append(
                {
                    "timestamp": ts,
                    "price": price,
                    "cvd": cvd,
                    "cvd_5min": self._number(row.get("cvd_5min")),
                    "cvd_ma_20": self._number(row.get("cvd_ma_20")),
                    "tick_volume": self._number(row.get("tick_volume")),
                    "aggressor": str(row.get("aggressor") or "neutral"),
                }
            )
        if not records:
            return pd.DataFrame(columns=["timestamp", "price", "cvd", "cvd_5min", "cvd_ma_20", "tick_volume", "aggressor"])
        return pd.DataFrame.from_records(records).sort_values("timestamp")

    def _load_volume_profile_levels(self, path: Path, trade_df: pd.DataFrame) -> List[Dict[str, Any]]:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                levels = payload.get("levels")
                if isinstance(levels, list):
                    return [level for level in levels if isinstance(level, dict)]
            except Exception:
                pass

        if trade_df.empty:
            return []
        grouped = (
            trade_df.groupby(["price_bin", "aggressor"], as_index=False)["quantity"]
            .sum()
            .pivot(index="price_bin", columns="aggressor", values="quantity")
            .fillna(0.0)
        )
        levels: List[Dict[str, Any]] = []
        for price, row in grouped.iterrows():
            buy = float(row.get("buy", 0.0))
            sell = float(row.get("sell", 0.0))
            neutral = float(row.get("neutral", 0.0))
            levels.append(
                {
                    "price": float(price),
                    "buy_volume": buy,
                    "sell_volume": sell,
                    "neutral_volume": neutral,
                    "total_volume": buy + sell + neutral,
                    "delta": buy - sell,
                }
            )
        return sorted(levels, key=lambda item: float(item.get("price") or 0.0))

    def _extract_expiry_list(self, response: Dict[str, Any]) -> List[str]:
        data = response.get("data")
        candidates: List[Any] = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            for key in ("expiryList", "expiries", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    candidates = value
                    break

        expiries: List[str] = []
        for item in candidates:
            raw = item.get("expiry") or item.get("date") or item.get("value") if isinstance(item, dict) else item
            parsed = self._parse_iso_date(raw)
            if parsed is not None:
                expiries.append(parsed.date().isoformat())
        return sorted(set(expiries))

    def _pick_nearest_expiry(self, expiries: List[str]) -> Optional[str]:
        if not expiries:
            return None
        today = pd.Timestamp.now(tz=self.config.market_timezone).normalize().tz_localize(None)
        dated = [(self._parse_iso_date(item), item) for item in expiries]
        valid = [(parsed, raw) for parsed, raw in dated if parsed is not None and parsed >= today]
        if not valid:
            return expiries[0]
        valid.sort(key=lambda item: item[0])
        return valid[0][1]

    def _extract_option_leg(self, payload: Any, option_type: str) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        greeks = payload.get("greeks") if isinstance(payload.get("greeks"), dict) else {}
        leg = {
            "option_type": option_type,
            "last_price": self._number(payload.get("last_price") or payload.get("ltp") or payload.get("lastTradedPrice") or payload.get("price")),
            "volume": self._coerce_int(payload.get("volume") or payload.get("tradedVolume")),
            "open_interest": self._coerce_int(payload.get("open_interest") or payload.get("oi") or payload.get("openInterest")),
            "change_in_open_interest": self._coerce_int(payload.get("change_in_open_interest") or payload.get("changeInOpenInterest") or payload.get("oi_change") or payload.get("changeOi")),
            "implied_volatility": self._number(payload.get("implied_volatility") or payload.get("iv") or payload.get("impliedVolatility")),
            "delta": self._number(payload.get("delta") or greeks.get("delta")),
            "gamma": self._number(payload.get("gamma") or greeks.get("gamma")),
            "theta": self._number(payload.get("theta") or greeks.get("theta")),
            "vega": self._number(payload.get("vega") or greeks.get("vega")),
            "bid_price": self._number(payload.get("bid_price") or payload.get("top_bid_price") or payload.get("bestBidPrice") or payload.get("bidPrice")),
            "ask_price": self._number(payload.get("ask_price") or payload.get("top_ask_price") or payload.get("bestAskPrice") or payload.get("askPrice")),
            "security_id": self._coerce_int(payload.get("security_id") or payload.get("securityId")),
        }
        if all(value is None or value == option_type for value in leg.values()):
            return None
        return leg

    def _flatten_option_chain_rows(
        self,
        payload: Any,
        rows: Optional[List[Dict[str, Any]]] = None,
        parent_strike: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        if rows is None:
            rows = []
        if isinstance(payload, list):
            for item in payload:
                self._flatten_option_chain_rows(item, rows, parent_strike)
            return rows
        if not isinstance(payload, dict):
            return rows

        nested_data = payload.get("data")
        if isinstance(nested_data, (dict, list)) and set(str(key) for key in payload.keys()).issubset({"data", "status", "remarks", "message"}):
            return self._flatten_option_chain_rows(nested_data, rows, parent_strike)
        for container_key in ("oc", "optionChain", "records"):
            if isinstance(payload.get(container_key), (dict, list)):
                return self._flatten_option_chain_rows(payload.get(container_key), rows, parent_strike)

        strike = self._number(payload.get("strike_price") or payload.get("strikePrice") or payload.get("strike") or parent_strike)
        call_payload = payload.get("call") or payload.get("CALL") or payload.get("ce") or payload.get("CE") or payload.get("callData")
        put_payload = payload.get("put") or payload.get("PUT") or payload.get("pe") or payload.get("PE") or payload.get("putData")
        if strike is not None and (isinstance(call_payload, dict) or isinstance(put_payload, dict)):
            rows.append(
                {
                    "strike_price": strike,
                    "call": self._extract_option_leg(call_payload, "CALL"),
                    "put": self._extract_option_leg(put_payload, "PUT"),
                }
            )
            return rows

        for key, value in payload.items():
            inferred_strike = strike if strike is not None else self._number(key)
            self._flatten_option_chain_rows(value, rows, inferred_strike)
        return rows

    def _option_chain_underlying_price(self, response: Dict[str, Any]) -> Optional[float]:
        data = response.get("data")
        if isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, dict):
                data = nested
            for key in ("underlyingPrice", "underlying_price", "underlyingValue", "spotPrice", "last_price"):
                value = self._number(data.get(key))
                if value is not None:
                    return value
        return None

    def _chart_paths(self, market_date: str) -> Dict[str, Path]:
        output_dir = self.config.nifty_depth_charts_dir / market_date
        output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "output_dir": output_dir,
            "heatmap": output_dir / "nifty_bookmap_heatmap.png",
            "footprint": output_dir / "nifty_order_flow_footprint.png",
            "dom": output_dir / "nifty_dom_ladder.png",
            "cvd": output_dir / "nifty_cvd_chart.png",
            "candle_5m": output_dir / "nifty_futures_5m_candles.png",
            "candle_15m": output_dir / "nifty_futures_15m_candles.png",
            "volume_profile": output_dir / "nifty_volume_profile.png",
            "option_chain_oi": output_dir / "nifty_option_chain_oi.png",
            "summary": output_dir / "chart_summary.json",
        }

    def generate_for_market_date(self, market_date: str) -> Dict[str, Any]:
        data_dir = self.config.nifty_depth_data_dir / market_date
        paths = self._chart_paths(market_date)
        depth_rows = self._load_ndjson(data_dir / "depth_200.ndjson", self.max_depth_packets)
        trade_tick_rows = self._load_ndjson(data_dir / "trade_ticks.ndjson", self.max_full_packets)
        full_rows = self._load_ndjson(data_dir / "full_market.ndjson", self.max_full_packets)
        cvd_rows = self._load_ndjson(data_dir / "cvd_series.ndjson", self.cvd_max_rows)

        depth_df = self._depth_dataframe(depth_rows)
        quote_df = self._best_quotes_from_depth(depth_rows)
        trade_tick_source = "trade_ticks.ndjson" if trade_tick_rows else "full_market.ndjson_fallback"
        trade_df = self._trade_tick_dataframe(trade_tick_rows) if trade_tick_rows else self._trade_dataframe(full_rows, quote_df)
        cvd_df = self._cvd_dataframe(cvd_rows)
        volume_profile_levels = self._load_volume_profile_levels(data_dir / "volume_profile.json", trade_df)

        if depth_df.empty and trade_df.empty:
            payload = self._build_summary(market_date, paths, depth_df, trade_df, generated=False, trade_tick_source=trade_tick_source)
            StorageService.save_snapshot(paths["summary"], payload)
            StorageService.save_snapshot(self.config.nifty_depth_charts_latest_path, payload)
            return payload

        extra_charts: Dict[str, Dict[str, Any]] = {}
        chart_errors: Dict[str, str] = {}
        self._render_bookmap_heatmap(depth_df, quote_df, trade_df, paths["heatmap"], market_date)
        self._render_footprint_chart(trade_df, paths["footprint"], market_date)
        self._render_dom_ladder(depth_rows, trade_df, paths["dom"], market_date)

        render_jobs = [
            (
                "cvd_chart",
                lambda: self._render_cvd_chart(cvd_df, trade_df, paths["cvd"], market_date),
                "Cumulative Volume Delta with NIFTY futures price for session order-flow divergence.",
                paths["cvd"],
            ),
            (
                "nifty_futures_5m_candles",
                lambda: self._render_nifty_candle_chart(5, paths["candle_5m"], market_date),
                "5-minute NIFTY futures technical chart with VWAP, EMAs, RSI, volume, and CVD proxy.",
                paths["candle_5m"],
            ),
            (
                "nifty_futures_15m_candles",
                lambda: self._render_nifty_candle_chart(15, paths["candle_15m"], market_date),
                "15-minute NIFTY futures higher-timeframe technical chart.",
                paths["candle_15m"],
            ),
            (
                "volume_profile",
                lambda: self._render_volume_profile(volume_profile_levels, paths["volume_profile"], market_date),
                "Session price-level volume profile with POC and value area.",
                paths["volume_profile"],
            ),
            (
                "option_chain_oi",
                lambda: self._render_option_chain_oi(paths["option_chain_oi"], market_date),
                "NIFTY option-chain open-interest distribution with call and put walls.",
                paths["option_chain_oi"],
            ),
        ]
        for key, render, description, path in render_jobs:
            try:
                meta = render() or {}
                extra_charts[key] = {
                    "path": str(path),
                    "description": description,
                    **meta,
                }
            except Exception as exc:
                chart_errors[key] = f"{type(exc).__name__}: {exc}"

        payload = self._build_summary(
            market_date,
            paths,
            depth_df,
            trade_df,
            generated=True,
            trade_tick_source=trade_tick_source,
            extra_charts=extra_charts,
            chart_errors=chart_errors,
            cvd_df=cvd_df,
            volume_profile_levels=volume_profile_levels,
        )
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
        extra_charts: Optional[Dict[str, Dict[str, Any]]] = None,
        chart_errors: Optional[Dict[str, str]] = None,
        cvd_df: Optional[pd.DataFrame] = None,
        volume_profile_levels: Optional[List[Dict[str, Any]]] = None,
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
        if extra_charts:
            charts.update(extra_charts)
        chart_paths_ordered = [info["path"] for info in charts.values()]
        cvd_summary: Dict[str, Any] = {}
        if cvd_df is not None and not cvd_df.empty:
            last = cvd_df.iloc[-1]
            cvd_summary = {
                "latest_cvd": round(float(last.get("cvd") or 0.0), 3),
                "latest_cvd_5min": round(float(last.get("cvd_5min") or 0.0), 3) if pd.notna(last.get("cvd_5min")) else None,
                "session_cvd_high": round(float(cvd_df["cvd"].max()), 3),
                "session_cvd_low": round(float(cvd_df["cvd"].min()), 3),
                "rows_used": len(cvd_df),
            }
        profile_summary: Dict[str, Any] = {}
        if volume_profile_levels:
            total_volume = sum(float(level.get("total_volume") or 0.0) for level in volume_profile_levels)
            poc = max(volume_profile_levels, key=lambda level: float(level.get("total_volume") or 0.0))
            profile_summary = {
                "price_levels": len(volume_profile_levels),
                "total_volume": round(total_volume, 3),
                "point_of_control": {
                    "price": poc.get("price"),
                    "volume": round(float(poc.get("total_volume") or 0.0), 3),
                },
            }
        return {
            "stage": "nifty_market_depth_charting",
            "generated": generated,
            "generated_at_utc": self._now_utc(),
            "market_date": market_date,
            "input": {
                "depth_rows_used": len(depth_df),
                "trade_rows_used": len(trade_df),
                "trade_tick_source": trade_tick_source,
                "sample_mode": self.sample_mode,
                "max_depth_packets": self.max_depth_packets,
                "max_full_packets": self.max_full_packets,
                "price_step": self.price_step,
                "footprint_minutes": self.footprint_minutes,
                "max_footprint_buckets": self.max_footprint_buckets,
            },
            "charts": charts,
            "chart_count": len(charts) if generated else 0,
            "chart_paths_ordered": chart_paths_ordered if generated else [],
            "chart_errors": chart_errors or {},
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
            "cvd_summary": cvd_summary,
            "volume_profile_summary": profile_summary,
            "limitations": [
                "Depth is real 200-level resting liquidity captured by our recorder.",
                "Footprint aggressor side is inferred from sampled full-market packets plus best bid/ask or tick direction.",
                "For exchange-grade footprint accuracy, reduce raw write throttling and persist every trade tick with matching bid/ask.",
            ],
        }

    def _render_cvd_chart(
        self,
        cvd_df: pd.DataFrame,
        trade_df: pd.DataFrame,
        output_path: Path,
        market_date: str,
    ) -> Dict[str, Any]:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        if cvd_df.empty and trade_df.empty:
            raise ValueError("No CVD or trade data available")

        if cvd_df.empty:
            df = trade_df.copy()
            signed = df["quantity"].where(df["aggressor"] == "buy", 0.0) - df["quantity"].where(df["aggressor"] == "sell", 0.0)
            cvd_df = pd.DataFrame({"timestamp": df["timestamp"], "price": df["price"], "cvd": signed.cumsum()})

        plot = cvd_df.copy().sort_values("timestamp")
        if "price" not in plot.columns or plot["price"].isna().all():
            if not trade_df.empty:
                prices = trade_df[["timestamp", "price"]].dropna().sort_values("timestamp")
                plot = pd.merge_asof(plot, prices, on="timestamp", direction="backward")

        plot["cvd_ma_20"] = plot["cvd_ma_20"] if "cvd_ma_20" in plot.columns else plot["cvd"].rolling(20, min_periods=1).mean()
        plot["cvd_ma_20"] = plot["cvd_ma_20"].fillna(plot["cvd"].rolling(20, min_periods=1).mean())

        fig, (ax_price, ax_cvd) = plt.subplots(2, 1, figsize=(17, 9), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.6]})
        fig.patch.set_facecolor("#101820")
        for ax in (ax_price, ax_cvd):
            ax.set_facecolor("#101820")
            ax.grid(True, color="#2f3f4a", linestyle=":", alpha=0.45)
            ax.tick_params(colors="#d7e2ea")

        if "price" in plot.columns and not plot["price"].isna().all():
            ax_price.plot(plot["timestamp"], plot["price"], color="#f7c948", linewidth=1.7, label="NIFTY futures price")
            price_delta = float(plot["price"].dropna().iloc[-1] - plot["price"].dropna().iloc[0])
        else:
            price_delta = 0.0
            ax_price.text(0.5, 0.5, "Price unavailable", transform=ax_price.transAxes, ha="center", va="center", color="white")

        cvd_values = plot["cvd"].astype(float)
        ax_cvd.plot(plot["timestamp"], cvd_values, color="#36d399", linewidth=1.8, label="CVD")
        ax_cvd.plot(plot["timestamp"], plot["cvd_ma_20"].astype(float), color="#60a5fa", linewidth=1.1, linestyle="--", label="CVD MA20")
        ax_cvd.fill_between(plot["timestamp"], cvd_values, 0, where=(cvd_values >= 0), color="#22c55e", alpha=0.20)
        ax_cvd.fill_between(plot["timestamp"], cvd_values, 0, where=(cvd_values < 0), color="#ef4444", alpha=0.20)
        ax_cvd.axhline(0, color="#d7e2ea", linestyle="--", linewidth=0.8, alpha=0.7)

        cvd_delta = float(cvd_values.iloc[-1] - cvd_values.iloc[0])
        divergence = "none"
        if price_delta > 0 and cvd_delta < 0:
            divergence = "bearish_price_up_cvd_down"
        elif price_delta < 0 and cvd_delta > 0:
            divergence = "bullish_price_down_cvd_up"
        if divergence != "none":
            ax_cvd.text(
                0.01,
                0.92,
                f"Divergence: {divergence.replace('_', ' ')}",
                transform=ax_cvd.transAxes,
                color="#ffb86b",
                fontsize=10,
                fontweight="bold",
            )

        ax_price.set_title(f"NIFTY Cumulative Volume Delta ({market_date})", color="white", fontsize=15)
        ax_price.legend(loc="upper left")
        ax_cvd.legend(loc="upper left")
        ax_cvd.set_ylabel("CVD", color="#d7e2ea")
        ax_cvd.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        fig.savefig(output_path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        return {
            "latest_cvd": round(float(cvd_values.iloc[-1]), 3),
            "session_cvd_high": round(float(cvd_values.max()), 3),
            "session_cvd_low": round(float(cvd_values.min()), 3),
            "divergence": divergence,
            "rows": len(plot),
        }

    def _render_volume_profile(self, levels: List[Dict[str, Any]], output_path: Path, market_date: str) -> Dict[str, Any]:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if not levels:
            raise ValueError("No volume profile levels available")
        levels = sorted(levels, key=lambda item: float(item.get("price") or 0.0))
        total_volume = sum(float(level.get("total_volume") or 0.0) for level in levels)
        if total_volume <= 0:
            raise ValueError("Volume profile total volume is zero")

        poc = max(levels, key=lambda item: float(item.get("total_volume") or 0.0))
        sorted_by_volume = sorted(levels, key=lambda item: float(item.get("total_volume") or 0.0), reverse=True)
        running = 0.0
        value_prices: List[float] = []
        for level in sorted_by_volume:
            running += float(level.get("total_volume") or 0.0)
            value_prices.append(float(level.get("price") or 0.0))
            if running >= total_volume * 0.70:
                break
        vah = max(value_prices) if value_prices else None
        val = min(value_prices) if value_prices else None

        prices = [float(level.get("price") or 0.0) for level in levels]
        volumes = [float(level.get("total_volume") or 0.0) for level in levels]
        colors = ["#16a34a" if float(level.get("delta") or 0.0) >= 0 else "#dc2626" for level in levels]

        fig, ax = plt.subplots(figsize=(10, 13))
        fig.patch.set_facecolor("#111827")
        ax.set_facecolor("#111827")
        ax.barh(prices, volumes, color=colors, alpha=0.82, height=max(self.price_step * 0.82, 0.8))
        ax.axhline(float(poc.get("price") or 0.0), color="#facc15", linewidth=2.2, label="POC")
        if vah is not None and val is not None:
            ax.axhspan(val, vah, color="#60a5fa", alpha=0.12, label="70% value area")
        ax.set_title(f"NIFTY Session Volume Profile ({market_date})", color="white", fontsize=14)
        ax.set_xlabel("Traded volume", color="#d7e2ea")
        ax.set_ylabel("Price", color="#d7e2ea")
        ax.tick_params(colors="#d7e2ea")
        ax.grid(True, axis="x", color="#334155", linestyle=":", alpha=0.5)
        ax.legend(loc="lower right")
        fig.savefig(output_path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        return {
            "point_of_control": {"price": poc.get("price"), "volume": round(float(poc.get("total_volume") or 0.0), 3)},
            "value_area_high": vah,
            "value_area_low": val,
            "total_volume": round(total_volume, 3),
            "price_levels": len(levels),
        }

    def _render_nifty_candle_chart(self, timeframe: int, output_path: Path, market_date: str) -> Dict[str, Any]:
        from pipeline.services.dhan_service import DhanService

        future = self.reference.find_front_month_future("NSE", "NIFTY")
        if not future:
            raise RuntimeError("Could not resolve front-month NIFTY future")

        dhan = DhanService(self.config)
        response = dhan.fetch_intraday_history(
            int(future["security_id"]),
            days=7,
            interval=1,
            exchange_segment="NSE_FNO",
            instrument_candidates=["FUTIDX"],
        )
        if not response or str(response.get("status", "")).lower() != "success":
            raise RuntimeError(f"Dhan intraday history failed: {(response or {}).get('remarks')}")
        frame = dhan.intraday_response_to_df(response)
        if frame.empty:
            raise ValueError("No NIFTY futures intraday candles returned")

        service = CandlestickChartService(
            self.config.market_timezone,
            market_open=(self.config.market_open_hour, self.config.market_open_minute),
            market_close=(self.config.market_close_hour, self.config.market_close_minute),
        )
        local_frame = service._to_market_frame(frame)
        day_frame = service._day_frame(local_frame, market_date)
        if day_frame.empty:
            raise ValueError(f"No NIFTY futures candles available for {market_date}")
        prev_date = service._previous_trading_day(market_date).isoformat()
        prev_frame = service._day_frame(local_frame, prev_date)
        prev_day_levels = service._compute_prev_day_levels(prev_frame) if not prev_frame.empty else {}
        resampled = service._resample_frame(day_frame, timeframe)
        enriched = service._compute_full_indicators(resampled)
        sr_levels = service._detect_support_resistance(enriched, prev_day_levels)
        sd_zones = service._detect_supply_demand_zones(enriched)
        patterns = service._detect_candlestick_patterns(enriched)
        service._render_chart(
            frame=enriched,
            title=f"NIFTY Futures {timeframe}m",
            subtitle=f"CURRENT DAY - {market_date}",
            output_path=output_path,
            market_date=market_date,
            timeframe_minutes=timeframe,
            sr_levels=sr_levels,
            sd_zones=sd_zones,
            patterns=patterns,
            prev_day_levels=prev_day_levels,
        )
        return {
            "security_id": int(future["security_id"]),
            "display_name": future.get("display_name"),
            "timeframe_minutes": timeframe,
            "candles": int(len(resampled)),
            "technical_metadata": service._build_technical_metadata(enriched, sr_levels, sd_zones, patterns, prev_day_levels),
        }

    def _render_option_chain_oi(self, output_path: Path, market_date: str) -> Dict[str, Any]:
        from pipeline.services.dhan_service import DhanService

        index = self.reference.find_index("NIFTY", "NSE")
        if not index:
            raise RuntimeError("Could not resolve NIFTY index for option chain")
        dhan = DhanService(self.config)
        expiry_response = dhan.fetch_option_chain_expiry_list(int(index["security_id"]), str(index["exchange_segment"]))
        if str(expiry_response.get("status", "")).lower() != "success":
            raise RuntimeError("Dhan option expiry list failed")
        expiry = self._pick_nearest_expiry(self._extract_expiry_list(expiry_response))
        if not expiry:
            raise RuntimeError("No option expiry available")
        chain_response = dhan.fetch_option_chain(int(index["security_id"]), str(index["exchange_segment"]), expiry)
        if str(chain_response.get("status", "")).lower() != "success":
            raise RuntimeError("Dhan option chain failed")
        rows = [row for row in self._flatten_option_chain_rows(chain_response.get("data")) if row.get("strike_price") is not None]
        if not rows:
            raise ValueError("Option chain returned no strike rows")
        rows.sort(key=lambda row: float(row["strike_price"]))
        underlying = self._option_chain_underlying_price(chain_response)
        atm = min(rows, key=lambda row: abs(float(row["strike_price"]) - float(underlying))) if underlying is not None else rows[len(rows) // 2]
        atm_index = rows.index(atm)
        start = max(0, atm_index - self.option_chain_strikes_each_side)
        end = min(len(rows), atm_index + self.option_chain_strikes_each_side + 1)
        selected = rows[start:end]

        strikes = [float(row["strike_price"]) for row in selected]
        call_oi = [float((row.get("call") or {}).get("open_interest") or 0.0) for row in selected]
        put_oi = [float((row.get("put") or {}).get("open_interest") or 0.0) for row in selected]
        total_call = sum(float((row.get("call") or {}).get("open_interest") or 0.0) for row in rows)
        total_put = sum(float((row.get("put") or {}).get("open_interest") or 0.0) for row in rows)
        pcr = total_put / total_call if total_call > 0 else None
        max_call_row = max(rows, key=lambda row: float((row.get("call") or {}).get("open_interest") or 0.0))
        max_put_row = max(rows, key=lambda row: float((row.get("put") or {}).get("open_interest") or 0.0))

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 11))
        fig.patch.set_facecolor("#0f172a")
        ax.set_facecolor("#0f172a")
        ax.barh(strikes, [-value for value in put_oi], color="#22c55e", alpha=0.80, label="Put OI")
        ax.barh(strikes, call_oi, color="#ef4444", alpha=0.80, label="Call OI")
        ax.axvline(0, color="#e2e8f0", linewidth=1.0)
        ax.axhline(float(atm["strike_price"]), color="#facc15", linewidth=2.0, label="ATM")
        ax.axhline(float(max_call_row["strike_price"]), color="#fb7185", linewidth=1.4, linestyle="--", label="Call wall")
        ax.axhline(float(max_put_row["strike_price"]), color="#86efac", linewidth=1.4, linestyle="--", label="Put wall")
        max_x = max(max(call_oi or [0.0]), max(put_oi or [0.0]), 1.0)
        ax.set_xlim(-max_x * 1.22, max_x * 1.22)
        ax.set_title(f"NIFTY Option Chain OI ({expiry})", color="white", fontsize=15)
        ax.set_xlabel("Put OI <- | -> Call OI", color="#d7e2ea")
        ax.set_ylabel("Strike", color="#d7e2ea")
        ax.tick_params(colors="#d7e2ea")
        ax.grid(True, axis="x", color="#334155", linestyle=":", alpha=0.45)
        pcr_text = f"PCR {pcr:.2f}" if pcr is not None else "PCR n/a"
        if underlying is not None:
            pcr_text += f" | Underlying {underlying:.2f}"
        ax.text(0.02, 0.97, pcr_text, transform=ax.transAxes, va="top", color="#f8fafc", fontsize=11, fontweight="bold")
        ax.legend(loc="lower right")
        fig.savefig(output_path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        return {
            "expiry": expiry,
            "underlying_price": round(float(underlying), 3) if underlying is not None else None,
            "atm_strike": float(atm["strike_price"]),
            "put_call_oi_ratio": round(pcr, 4) if pcr is not None else None,
            "max_call_oi_strike": float(max_call_row["strike_price"]),
            "max_put_oi_strike": float(max_put_row["strike_price"]),
            "strikes_rendered": len(selected),
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
        if len(buckets) > self.max_footprint_buckets:
            if self.sample_mode in {"span", "full_day", "full-session", "full_session"}:
                indexes = {
                    round(index * (len(buckets) - 1) / (self.max_footprint_buckets - 1))
                    for index in range(self.max_footprint_buckets)
                }
                buckets = [bucket for index, bucket in enumerate(buckets) if index in indexes]
            else:
                buckets = buckets[-self.max_footprint_buckets :]
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
