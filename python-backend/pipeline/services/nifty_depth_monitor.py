from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import redirect_stdout
from io import StringIO
import json
import os
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dhanhq import FullDepth, MarketFeed

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_reference_service import MarketReferenceService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.nifty_depth_charting import NiftyDepthChartGenerator
from pipeline.services.storage_service import StorageService


class NiftyDepthMonitor:
    """
    Stable NIFTY-only market-structure recorder.

    It records the front-month NIFTY future because the NIFTY index itself is
    not a tradeable order book. The standard MarketFeed.Full stream captures
    trade/full-packet data, while FullDepth(depth_level=200) captures the deep
    order book for the same primary instrument.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.market_time = MarketTimeService(config)
        self.reference = MarketReferenceService(config)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()

        self.enabled = self._env_bool("NIFTY_DEPTH_MONITOR_ENABLED", True)
        self.depth_level = self._env_int("NIFTY_DEPTH_LEVEL", 200)
        self.reconnect_delay_seconds = self._env_float("NIFTY_DEPTH_RECONNECT_SECONDS", 5.0)
        self.latest_save_interval_seconds = self._env_float("NIFTY_DEPTH_LATEST_SAVE_SECONDS", 5.0)
        self.raw_write_interval_seconds = self._env_float("NIFTY_DEPTH_RAW_WRITE_SECONDS", 0.0)
        self.persist_every_packet = self._env_bool("NIFTY_DEPTH_PERSIST_EVERY_PACKET", True)
        self.first_packet_timeout_seconds = self._env_float("NIFTY_DEPTH_FIRST_PACKET_TIMEOUT_SECONDS", 20.0)
        self.max_latest_depth_levels = self._env_int("NIFTY_DEPTH_LATEST_LEVELS", 20)
        self.charts_enabled = self._env_bool("NIFTY_DEPTH_CHARTS_ENABLED", True)
        self.chart_interval_seconds = self._env_float("NIFTY_DEPTH_CHART_INTERVAL_SECONDS", 60.0)
        self.depth_imbalance_interval_seconds = self._env_float("NIFTY_DEPTH_IMBALANCE_SECONDS", 30.0)
        self.large_order_threshold = self._env_float("NIFTY_LARGE_ORDER_THRESHOLD", 300.0)
        self.large_order_hysteresis = self._env_float("NIFTY_LARGE_ORDER_HYSTERESIS", 0.80)
        self.volume_profile_save_interval_seconds = self._env_float("NIFTY_VOLUME_PROFILE_SAVE_SECONDS", 300.0)
        self.options_feed_enabled = self._env_bool("NIFTY_OPTIONS_FEED_ENABLED", True)
        self.options_strikes_each_side = self._env_int("NIFTY_OPTIONS_STRIKES_EACH_SIDE", 2)
        self.options_price_wait_seconds = self._env_float("NIFTY_OPTIONS_PRICE_WAIT_SECONDS", 180.0)
        self.charting = NiftyDepthChartGenerator(config)

        self.data_dir = self.config.nifty_depth_data_dir
        self.latest_path = self.config.nifty_depth_latest_path
        self.targets: Dict[str, Any] = {}
        self.latest_full_packet: Optional[Dict[str, Any]] = None
        self.latest_depth_sides: Dict[str, Dict[str, Any]] = {}
        self.last_saved_at = 0.0
        self.last_raw_write_at: Dict[str, float] = {}
        self.started_threads = False
        self.started_at_utc = datetime.now(timezone.utc).isoformat()
        self.last_error_by_stream: Dict[str, str] = {}
        self.last_packet_at_utc_by_stream: Dict[str, str] = {}
        self.stream_states: Dict[str, Dict[str, Any]] = {}
        self.event_sequence_by_stream: Dict[str, int] = {}
        self.previous_trade_volume: Optional[float] = None
        self.previous_trade_price: Optional[float] = None
        self.last_trade_fingerprint: Optional[str] = None
        self.cumulative_buy_volume = 0.0
        self.cumulative_sell_volume = 0.0
        self.cumulative_neutral_volume = 0.0
        self.cvd_window: deque[tuple[float, float]] = deque()
        self.cvd_ma_window: deque[float] = deque(maxlen=20)
        self.volume_profile: Dict[float, Dict[str, float]] = defaultdict(lambda: {"buy": 0.0, "sell": 0.0, "neutral": 0.0, "total": 0.0})
        self.last_volume_profile_save_at = 0.0
        self.last_depth_imbalance_saved_at = 0.0
        self.active_large_orders: Dict[str, Dict[str, Any]] = {}
        self.option_instruments_by_id: Dict[str, Dict[str, Any]] = {}
        self.latest_option_packets: Dict[str, Dict[str, Any]] = {}
        self.metrics = {
            "full_market_packets": 0,
            "depth_200_packets": 0,
            "depth_200_bid_packets": 0,
            "depth_200_ask_packets": 0,
            "trade_ticks_written": 0,
            "cvd_updates_written": 0,
            "depth_imbalance_snapshots_written": 0,
            "large_order_events_written": 0,
            "volume_profile_updates_written": 0,
            "options_packets_written": 0,
            "raw_events_written": 0,
            "reconnects": 0,
            "no_packet_timeouts": 0,
            "chart_generations": 0,
            "chart_errors": 0,
        }

    def _env_bool(self, key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

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

    def _market_date(self) -> str:
        return self.market_time.market_date_str()

    def _daily_dir(self) -> Path:
        path = self.data_dir / self._market_date()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        return value

    def _wait_for_market_hours(self, stream_name: str) -> None:
        while not self.stop_event.is_set() and not self.market_time.is_market_hours():
            self._save_latest(
                status="waiting_for_market_open",
                force=True,
                stream_name=stream_name,
            )
            time.sleep(30)

    def _resolve_targets(self) -> Dict[str, Any]:
        override_security_id = os.getenv("NIFTY_DEPTH_SECURITY_ID")
        override_display_name = os.getenv("NIFTY_DEPTH_DISPLAY_NAME", "NIFTY FUT OVERRIDE")

        index_row = self.reference.find_index("NIFTY", "NSE") or {
            "security_id": 13,
            "exchange_segment": "IDX_I",
            "symbol": "NIFTY",
            "display_name": "NIFTY 50",
        }

        if override_security_id:
            future_row = {
                "security_id": int(override_security_id),
                "exchange_segment": "NSE_FNO",
                "symbol": "NIFTY",
                "display_name": override_display_name,
                "instrument": "FUTIDX",
                "underlying_symbol": "NIFTY",
                "expiry_date": None,
            }
        else:
            future_row = self.reference.find_front_month_future("NSE", "NIFTY")
            if not future_row:
                raise RuntimeError(
                    "Could not resolve front-month NIFTY future from security_id_list.csv. "
                    "Set NIFTY_DEPTH_SECURITY_ID to force a contract."
                )
            future_row = dict(future_row)
            future_row["exchange_segment"] = "NSE_FNO"

        return self._json_safe({
            "underlying_index": index_row,
            "primary_depth_instrument": future_row,
            "depth_level": self.depth_level,
            "resolved_at_utc": self._now_utc(),
        })

    def _ensure_targets(self) -> Dict[str, Any]:
        with self.lock:
            if not self.targets:
                self.targets = self._resolve_targets()
            return dict(self.targets)

    def _exchange_constant(self, cls: Any, exchange_segment: str) -> Any:
        normalized = str(exchange_segment or "").upper()
        if normalized == "NSE_FNO" and hasattr(cls, "NSE_FNO"):
            return getattr(cls, "NSE_FNO")
        if normalized == "BSE_FNO" and hasattr(cls, "BSE_FNO"):
            return getattr(cls, "BSE_FNO")
        if normalized.startswith("BSE"):
            return getattr(cls, "BSE")
        return getattr(cls, "NSE")

    def _set_stream_state(self, stream_name: str, **updates: Any) -> None:
        with self.lock:
            state = dict(self.stream_states.get(stream_name) or {})
            state.update(self._json_safe(updates))
            state["updated_at_utc"] = self._now_utc()
            self.stream_states[stream_name] = state

    def _close_feed(self, feed: Any) -> None:
        if feed is None:
            return
        for method_name in ("close_connection", "disconnect"):
            method = getattr(feed, method_name, None)
            if not method:
                continue
            try:
                method()
                return
            except Exception:
                continue

    def _append_event(self, stream_name: str, payload: Dict[str, Any], *, throttle: bool = True) -> None:
        now = time.time()
        if throttle and self.raw_write_interval_seconds > 0:
            last_write = self.last_raw_write_at.get(stream_name, 0.0)
            if now - last_write < self.raw_write_interval_seconds:
                return
            self.last_raw_write_at[stream_name] = now

        payload = dict(payload)
        payload.setdefault("captured_at_utc", self._now_utc())
        payload.setdefault("captured_monotonic_ns", time.monotonic_ns())
        payload.setdefault("event_sequence", self._next_event_sequence(stream_name))
        path = self._daily_dir() / f"{stream_name}.ndjson"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, default=str))
            handle.write("\n")
        with self.lock:
            self.metrics["raw_events_written"] += 1

    def _next_event_sequence(self, stream_name: str) -> int:
        with self.lock:
            value = int(self.event_sequence_by_stream.get(stream_name, 0)) + 1
            self.event_sequence_by_stream[stream_name] = value
            return value

    def _first_number(self, payload: Any, keys: tuple[str, ...]) -> Optional[float]:
        if isinstance(payload, dict):
            for key in keys:
                if key in payload and payload.get(key) not in (None, ""):
                    try:
                        return float(payload.get(key))
                    except Exception:
                        continue
            for value in payload.values():
                nested = self._first_number(value, keys)
                if nested is not None:
                    return nested
        elif isinstance(payload, list):
            for value in payload:
                nested = self._first_number(value, keys)
                if nested is not None:
                    return nested
        return None

    def _normalize_level(self, level: Any, side: str) -> Dict[str, Any]:
        if not isinstance(level, dict):
            return {"raw": level}

        price = self._first_number(
            level,
            ("price", f"{side}_price", f"{side}Price", "bid_price", "ask_price"),
        )
        quantity = self._first_number(
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
        orders = self._first_number(
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
        return {
            "price": price,
            "quantity": quantity,
            "orders": int(orders) if orders is not None else None,
        }

    def _normalize_depth_levels(self, levels: Any, side: str) -> List[Dict[str, Any]]:
        if not isinstance(levels, list):
            return []
        return [self._normalize_level(level, side) for level in levels]

    def _side_key(self, raw_type: Any) -> str:
        text = str(raw_type or "").strip().lower()
        if text.startswith("ask") or text.startswith("sell"):
            return "ask"
        return "bid"

    def _summarize_side(self, side_payload: Optional[Dict[str, Any]], side: str) -> Dict[str, Any]:
        if not side_payload:
            return {"levels": 0, "total_quantity": 0, "top_price": None, "top_quantity": None}
        levels = self._normalize_depth_levels(side_payload.get("depth"), side)
        total_quantity = sum(float(level.get("quantity") or 0.0) for level in levels)
        top = levels[0] if levels else {}
        return {
            "levels": len(levels),
            "total_quantity": round(total_quantity, 3),
            "top_price": top.get("price"),
            "top_quantity": top.get("quantity"),
        }

    def _build_depth_snapshot(self) -> Dict[str, Any]:
        bid_payload = self.latest_depth_sides.get("bid")
        ask_payload = self.latest_depth_sides.get("ask")
        bid_summary = self._summarize_side(bid_payload, "bid")
        ask_summary = self._summarize_side(ask_payload, "ask")
        bid_qty = float(bid_summary.get("total_quantity") or 0.0)
        ask_qty = float(ask_summary.get("total_quantity") or 0.0)
        imbalance = None
        if bid_qty + ask_qty > 0:
            imbalance = round((bid_qty - ask_qty) / (bid_qty + ask_qty), 6)

        return {
            "bid_summary": bid_summary,
            "ask_summary": ask_summary,
            "depth_imbalance": imbalance,
            "bid_levels": self._normalize_depth_levels(
                (bid_payload or {}).get("depth"),
                "bid",
            )[: self.max_latest_depth_levels],
            "ask_levels": self._normalize_depth_levels(
                (ask_payload or {}).get("depth"),
                "ask",
            )[: self.max_latest_depth_levels],
        }

    def _build_full_packet_snapshot(self) -> Optional[Dict[str, Any]]:
        packet = self.latest_full_packet
        if not packet:
            return None
        return {
            "security_id": packet.get("security_id"),
            "exchange_segment": packet.get("exchange_segment"),
            "latest_price": self._first_number(
                packet,
                ("last_price", "lastPrice", "ltp", "LTP", "latest_traded_price"),
            ),
            "last_traded_quantity": self._first_number(
                packet,
                ("last_traded_quantity", "lastTradedQuantity", "last_quantity", "LTQ"),
            ),
            "volume": self._first_number(packet, ("volume", "Volume", "total_volume")),
            "open_interest": self._first_number(packet, ("open_interest", "openInterest", "oi", "OI")),
            "raw_keys": sorted(str(key) for key in packet.keys()) if isinstance(packet, dict) else [],
        }

    def _build_derived_snapshot(self) -> Dict[str, Any]:
        cvd = self.cumulative_buy_volume - self.cumulative_sell_volume
        profile_items = sorted(
            self.volume_profile.items(),
            key=lambda item: item[1].get("total", 0.0),
            reverse=True,
        )
        return {
            "cvd": {
                "cumulative_buy_volume": round(self.cumulative_buy_volume, 3),
                "cumulative_sell_volume": round(self.cumulative_sell_volume, 3),
                "cumulative_neutral_volume": round(self.cumulative_neutral_volume, 3),
                "cvd": round(cvd, 3),
                "cvd_ma_20": round(sum(self.cvd_ma_window) / len(self.cvd_ma_window), 3) if self.cvd_ma_window else None,
            },
            "volume_profile": {
                "price_levels": len(self.volume_profile),
                "point_of_control": (
                    {
                        "price": profile_items[0][0],
                        "volume": round(profile_items[0][1].get("total", 0.0), 3),
                    }
                    if profile_items
                    else None
                ),
                "last_saved_at_utc": datetime.fromtimestamp(self.last_volume_profile_save_at, timezone.utc).isoformat()
                if self.last_volume_profile_save_at
                else None,
            },
            "large_order_monitor": {
                "threshold": self.large_order_threshold,
                "active_count": len(self.active_large_orders),
                "active_nearest": list(self.active_large_orders.values())[:10],
            },
        }

    def _build_options_snapshot(self) -> Dict[str, Any]:
        packets = list(self.latest_option_packets.values())
        packets.sort(key=lambda item: (float(item.get("strike_price") or 0.0), str(item.get("option_type") or "")))
        return {
            "enabled": self.options_feed_enabled,
            "strikes_each_side": self.options_strikes_each_side,
            "instrument_count": len(self.option_instruments_by_id),
            "latest_packets": packets[:20],
        }

    def _current_ltp(self) -> Optional[float]:
        packet = self.latest_full_packet
        if not packet:
            return None
        return self._first_number(packet, ("last_price", "lastPrice", "ltp", "LTP", "latest_traded_price"))

    def _tick_quantity(self, tick: Dict[str, Any]) -> float:
        quantity = self._first_number(tick, ("volume_delta",))
        if quantity is None or quantity <= 0:
            quantity = self._first_number(tick, ("last_traded_quantity",)) or 0.0
        return float(quantity or 0.0)

    def _record_cvd_update(self, tick: Dict[str, Any]) -> None:
        quantity = self._tick_quantity(tick)
        if quantity <= 0:
            return

        aggressor = str(tick.get("aggressor") or "neutral").lower()
        if aggressor == "buy":
            self.cumulative_buy_volume += quantity
            signed_delta = quantity
        elif aggressor == "sell":
            self.cumulative_sell_volume += quantity
            signed_delta = -quantity
        else:
            self.cumulative_neutral_volume += quantity
            signed_delta = 0.0

        now = time.time()
        self.cvd_window.append((now, signed_delta))
        while self.cvd_window and now - self.cvd_window[0][0] > 300:
            self.cvd_window.popleft()

        cvd = self.cumulative_buy_volume - self.cumulative_sell_volume
        self.cvd_ma_window.append(cvd)
        payload = {
            "type": "cvd_update",
            "timestamp_ist": self.market_time.now().isoformat(),
            "latest_price": tick.get("latest_price"),
            "aggressor": aggressor,
            "tick_volume": round(quantity, 3),
            "volume_delta": tick.get("volume_delta"),
            "cumulative_buy_volume": round(self.cumulative_buy_volume, 3),
            "cumulative_sell_volume": round(self.cumulative_sell_volume, 3),
            "cumulative_neutral_volume": round(self.cumulative_neutral_volume, 3),
            "cvd": round(cvd, 3),
            "cvd_5min": round(sum(delta for _, delta in self.cvd_window), 3),
            "cvd_ma_20": round(sum(self.cvd_ma_window) / len(self.cvd_ma_window), 3) if self.cvd_ma_window else None,
            "best_bid": tick.get("best_bid"),
            "best_ask": tick.get("best_ask"),
            "classification_method": tick.get("classification_method"),
        }
        self._append_event("cvd_series", payload, throttle=False)
        with self.lock:
            self.metrics["cvd_updates_written"] += 1

    def _update_volume_profile(self, tick: Dict[str, Any]) -> None:
        quantity = self._tick_quantity(tick)
        price = self._first_number(tick, ("latest_price",))
        if quantity <= 0 or price is None:
            return

        price_bin = round(round(price / 1.0) * 1.0, 2)
        aggressor = str(tick.get("aggressor") or "neutral").lower()
        if aggressor not in {"buy", "sell", "neutral"}:
            aggressor = "neutral"

        bucket = self.volume_profile[price_bin]
        bucket[aggressor] = bucket.get(aggressor, 0.0) + quantity
        bucket["total"] = bucket.get("total", 0.0) + quantity
        self._save_volume_profile_if_due()

    def _save_volume_profile_if_due(self, *, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.last_volume_profile_save_at < self.volume_profile_save_interval_seconds:
            return
        if not self.volume_profile:
            return

        levels = [
            {
                "price": price,
                "buy_volume": round(values.get("buy", 0.0), 3),
                "sell_volume": round(values.get("sell", 0.0), 3),
                "neutral_volume": round(values.get("neutral", 0.0), 3),
                "total_volume": round(values.get("total", 0.0), 3),
                "delta": round(values.get("buy", 0.0) - values.get("sell", 0.0), 3),
            }
            for price, values in sorted(self.volume_profile.items())
        ]
        total_volume = sum(level["total_volume"] for level in levels)
        poc = max(levels, key=lambda item: item["total_volume"]) if levels else None
        payload = {
            "type": "volume_profile",
            "generated_at_utc": self._now_utc(),
            "generated_at_ist": self.market_time.now().isoformat(),
            "market_date": self._market_date(),
            "total_volume": round(total_volume, 3),
            "point_of_control": poc,
            "levels": levels,
        }
        try:
            StorageService.save_snapshot(self._daily_dir() / "volume_profile.json", payload)
            self.last_volume_profile_save_at = now
            with self.lock:
                self.metrics["volume_profile_updates_written"] += 1
        except Exception as exc:
            self.last_error_by_stream["volume_profile_writer"] = f"{type(exc).__name__}: {exc}"

    def _record_depth_imbalance_snapshot(self) -> None:
        now = time.time()
        if now - self.last_depth_imbalance_saved_at < self.depth_imbalance_interval_seconds:
            return

        bid_payload = self.latest_depth_sides.get("bid")
        ask_payload = self.latest_depth_sides.get("ask")
        if not bid_payload or not ask_payload:
            return

        bid_levels = self._normalize_depth_levels(bid_payload.get("depth"), "bid")
        ask_levels = self._normalize_depth_levels(ask_payload.get("depth"), "ask")
        if not bid_levels or not ask_levels:
            return

        bid_qty = sum(float(level.get("quantity") or 0.0) for level in bid_levels)
        ask_qty = sum(float(level.get("quantity") or 0.0) for level in ask_levels)
        if bid_qty + ask_qty <= 0:
            return

        bid_top5 = sum(float(level.get("quantity") or 0.0) for level in bid_levels[:5])
        ask_top5 = sum(float(level.get("quantity") or 0.0) for level in ask_levels[:5])
        largest_bid = max(bid_levels, key=lambda level: float(level.get("quantity") or 0.0), default=None)
        largest_ask = max(ask_levels, key=lambda level: float(level.get("quantity") or 0.0), default=None)
        bid_avg = bid_qty / len(bid_levels)
        ask_avg = ask_qty / len(ask_levels)
        payload = {
            "type": "depth_imbalance_snapshot",
            "timestamp_ist": self.market_time.now().isoformat(),
            "latest_price": self._current_ltp(),
            "bid_total_qty": round(bid_qty, 3),
            "ask_total_qty": round(ask_qty, 3),
            "imbalance": round((bid_qty - ask_qty) / (bid_qty + ask_qty), 6),
            "bid_top5_qty": round(bid_top5, 3),
            "ask_top5_qty": round(ask_top5, 3),
            "top5_imbalance": round((bid_top5 - ask_top5) / (bid_top5 + ask_top5), 6) if bid_top5 + ask_top5 > 0 else None,
            "largest_bid": largest_bid,
            "largest_ask": largest_ask,
            "bid_levels_above_avg": sum(1 for level in bid_levels if float(level.get("quantity") or 0.0) > bid_avg),
            "ask_levels_above_avg": sum(1 for level in ask_levels if float(level.get("quantity") or 0.0) > ask_avg),
        }
        self._append_event("depth_imbalance_series", payload, throttle=False)
        self.last_depth_imbalance_saved_at = now
        with self.lock:
            self.metrics["depth_imbalance_snapshots_written"] += 1

    def _record_large_order_events(self, side: str, levels: List[Dict[str, Any]]) -> None:
        current: Dict[str, Dict[str, Any]] = {}
        ltp = self._current_ltp()
        for level in levels:
            price = self._first_number(level, ("price",))
            quantity = self._first_number(level, ("quantity",))
            if price is None or quantity is None:
                continue
            key = f"{side}:{price:.2f}"
            if quantity >= self.large_order_threshold:
                current[key] = {
                    "side": side,
                    "price": price,
                    "quantity": quantity,
                    "orders": level.get("orders"),
                    "ltp_at_event": ltp,
                    "distance_from_ltp": round(price - ltp, 3) if ltp is not None else None,
                    "distance_percent": round(((price - ltp) / ltp) * 100, 4) if ltp else None,
                }

        previous_keys = {key for key in self.active_large_orders if key.startswith(f"{side}:")}
        current_keys = set(current)
        events: List[Dict[str, Any]] = []
        for key in sorted(current_keys - previous_keys):
            payload = dict(current[key])
            payload.update({"type": "large_order_appeared", "timestamp_ist": self.market_time.now().isoformat(), "threshold": self.large_order_threshold})
            events.append(payload)

        removal_threshold = self.large_order_threshold * self.large_order_hysteresis
        for key in sorted(previous_keys - current_keys):
            previous = self.active_large_orders.get(key) or {}
            price = previous.get("price")
            same_level = next((level for level in levels if self._first_number(level, ("price",)) == price), None)
            quantity = self._first_number(same_level or {}, ("quantity",)) if same_level else 0.0
            if quantity and quantity >= removal_threshold:
                continue
            payload = dict(previous)
            payload.update({
                "type": "large_order_removed",
                "timestamp_ist": self.market_time.now().isoformat(),
                "quantity": quantity or 0.0,
                "previous_quantity": previous.get("quantity"),
                "threshold": self.large_order_threshold,
            })
            events.append(payload)

        for key in previous_keys:
            self.active_large_orders.pop(key, None)
        self.active_large_orders.update(current)

        for event in events:
            self._append_event("large_order_events", event, throttle=False)
        if events:
            with self.lock:
                self.metrics["large_order_events_written"] += len(events)

    def _first_value(self, payload: Any, keys: tuple[str, ...]) -> Optional[Any]:
        if isinstance(payload, dict):
            for key in keys:
                if key in payload and payload.get(key) not in (None, ""):
                    return payload.get(key)
            for value in payload.values():
                nested = self._first_value(value, keys)
                if nested not in (None, ""):
                    return nested
        elif isinstance(payload, list):
            for value in payload:
                nested = self._first_value(value, keys)
                if nested not in (None, ""):
                    return nested
        return None

    def _best_bid_ask_from_packet(self, packet: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        best_bid = self._first_number(packet, ("best_bid", "bestBid", "best_bid_price", "bid_price"))
        best_ask = self._first_number(packet, ("best_ask", "bestAsk", "best_ask_price", "ask_price"))
        depth = packet.get("depth") if isinstance(packet, dict) else None
        if isinstance(depth, list):
            bid_prices: List[float] = []
            ask_prices: List[float] = []
            for level in depth:
                if not isinstance(level, dict):
                    continue
                bid = self._first_number(level, ("bid_price", "bidPrice", "best_bid_price"))
                ask = self._first_number(level, ("ask_price", "askPrice", "best_ask_price"))
                if bid is not None and bid > 0:
                    bid_prices.append(bid)
                if ask is not None and ask > 0:
                    ask_prices.append(ask)
            if bid_prices:
                best_bid = max(bid_prices)
            if ask_prices:
                best_ask = min(ask_prices)
        elif isinstance(depth, dict):
            bid_levels = self._normalize_depth_levels(depth.get("buy") or depth.get("bids"), "bid")
            ask_levels = self._normalize_depth_levels(depth.get("sell") or depth.get("asks"), "ask")
            bid_prices = [float(level.get("price") or 0.0) for level in bid_levels if level.get("price")]
            ask_prices = [float(level.get("price") or 0.0) for level in ask_levels if level.get("price")]
            if bid_prices:
                best_bid = max(bid_prices)
            if ask_prices:
                best_ask = min(ask_prices)
        return best_bid, best_ask

    def _build_trade_tick(self, packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        latest_price = self._first_number(
            packet,
            ("last_price", "lastPrice", "ltp", "LTP", "latest_traded_price"),
        )
        if latest_price is None:
            return None

        volume = self._first_number(packet, ("volume", "Volume", "total_volume"))
        last_quantity = self._first_number(
            packet,
            ("last_traded_quantity", "lastTradedQuantity", "last_quantity", "lastQuantity", "LTQ"),
        )
        last_trade_time = self._first_value(
            packet,
            ("last_traded_time", "lastTradedTime", "last_trade_time", "lastTradeTime", "LTT"),
        )
        open_interest = self._first_number(packet, ("open_interest", "openInterest", "oi", "OI"))
        best_bid, best_ask = self._best_bid_ask_from_packet(packet)

        volume_delta = None
        if volume is not None and self.previous_trade_volume is not None and volume >= self.previous_trade_volume:
            volume_delta = volume - self.previous_trade_volume

        aggressor = "neutral"
        classification_method = "unclassified"
        if best_ask is not None and latest_price >= best_ask:
            aggressor = "buy"
            classification_method = "ltp_at_or_above_best_ask"
        elif best_bid is not None and latest_price <= best_bid:
            aggressor = "sell"
            classification_method = "ltp_at_or_below_best_bid"
        elif self.previous_trade_price is not None and latest_price > self.previous_trade_price:
            aggressor = "buy"
            classification_method = "uptick_fallback"
        elif self.previous_trade_price is not None and latest_price < self.previous_trade_price:
            aggressor = "sell"
            classification_method = "downtick_fallback"

        self.previous_trade_volume = volume if volume is not None else self.previous_trade_volume
        self.previous_trade_price = latest_price

        return {
            "type": "trade_tick",
            "security_id": packet.get("security_id"),
            "exchange_segment": packet.get("exchange_segment"),
            "latest_price": latest_price,
            "last_traded_quantity": last_quantity,
            "last_trade_time": last_trade_time,
            "volume": volume,
            "volume_delta": volume_delta,
            "open_interest": open_interest,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "aggressor": aggressor,
            "classification_method": classification_method,
        }

    def _should_write_trade_tick(self, tick: Dict[str, Any]) -> bool:
        if self.persist_every_packet:
            return True
        fingerprint = json.dumps(
            {
                "ltp": tick.get("latest_price"),
                "ltq": tick.get("last_traded_quantity"),
                "ltt": tick.get("last_trade_time"),
                "volume": tick.get("volume"),
            },
            sort_keys=True,
        )
        if fingerprint == self.last_trade_fingerprint:
            return False
        self.last_trade_fingerprint = fingerprint
        return True

    def _save_latest(
        self,
        *,
        status: str = "recording",
        force: bool = False,
        stream_name: Optional[str] = None,
    ) -> None:
        now = time.time()
        if not force and now - self.last_saved_at < self.latest_save_interval_seconds:
            return

        with self.lock:
            payload = {
                "stage": "nifty_market_structure_monitor",
                "generated_at_utc": self._now_utc(),
                "generated_at_ist": self.market_time.now().isoformat(),
                "summary": {
                    "status": status,
                    "enabled": self.enabled,
                    "market_date": self._market_date(),
                    "market_timezone": self.config.market_timezone,
                    "is_market_hours": self.market_time.is_market_hours(),
                    "started_at_utc": self.started_at_utc,
                    "active_stream": stream_name,
                    "data_dir": str(self._daily_dir()),
                    "latest_path": str(self.latest_path),
                    "persist_every_packet": self.persist_every_packet,
                    "raw_write_interval_seconds": self.raw_write_interval_seconds,
                },
                "targets": self.targets,
                "metrics": dict(self.metrics),
                "stream_states": dict(self.stream_states),
                "last_packet_at_utc_by_stream": dict(self.last_packet_at_utc_by_stream),
                "last_error_by_stream": dict(self.last_error_by_stream),
                "latest_full_packet": self._build_full_packet_snapshot(),
                "latest_depth_200": self._build_depth_snapshot(),
                "derived_signals": self._build_derived_snapshot(),
                "options_feed": self._build_options_snapshot(),
            }
            payload = self._json_safe(payload)
            try:
                StorageService.save_snapshot(self.latest_path, payload)
                StorageService.save_snapshot(self._daily_dir() / "latest.json", payload)
            except Exception as exc:
                text = f"{type(exc).__name__}: {exc}"
                self.last_error_by_stream["snapshot_writer"] = text
                print(f"NIFTY depth monitor snapshot write error: {text}")
            self.last_saved_at = now

    def _record_error(self, stream_name: str, exc: Exception) -> None:
        text = f"{type(exc).__name__}: {exc}"
        print(f"NIFTY depth monitor {stream_name} error: {text}")
        with self.lock:
            self.last_error_by_stream[stream_name] = text
            self.metrics["reconnects"] += 1
        self._set_stream_state(stream_name, status="error", last_error=text)
        self._append_event(
            "errors",
            {"stream": stream_name, "error": text},
            throttle=False,
        )
        self._save_latest(status="stream_error", force=True, stream_name=stream_name)

    def _record_full_packet(self, packet: Dict[str, Any]) -> None:
        with self.lock:
            self.latest_full_packet = packet
            self.metrics["full_market_packets"] += 1
            self.last_packet_at_utc_by_stream["full_market"] = self._now_utc()
        self._set_stream_state("full_market", status="receiving", last_packet_at_utc=self._now_utc())
        self._append_event(
            "full_market",
            {"type": "full_market_packet", "packet": packet},
            throttle=not self.persist_every_packet,
        )
        trade_tick = self._build_trade_tick(packet)
        if trade_tick and self._should_write_trade_tick(trade_tick):
            self._append_event("trade_ticks", trade_tick, throttle=not self.persist_every_packet)
            self._record_cvd_update(trade_tick)
            self._update_volume_profile(trade_tick)
            with self.lock:
                self.metrics["trade_ticks_written"] += 1
        self._save_latest(stream_name="full_market")

    def _record_depth_packet(self, update: Dict[str, Any]) -> None:
        side = self._side_key(update.get("type"))
        with self.lock:
            self.latest_depth_sides[side] = update
            self.metrics["depth_200_packets"] += 1
            if side == "bid":
                self.metrics["depth_200_bid_packets"] += 1
            else:
                self.metrics["depth_200_ask_packets"] += 1
            self.last_packet_at_utc_by_stream["depth_200"] = self._now_utc()
        self._set_stream_state("depth_200", status="receiving", last_packet_at_utc=self._now_utc())
        self._append_event(
            "depth_200",
            {
                "type": "depth_200_packet",
                "side": side,
                "exchange_segment": update.get("exchange_segment"),
                "security_id": update.get("security_id"),
                "depth": update.get("depth"),
            },
            throttle=not self.persist_every_packet,
        )
        levels = self._normalize_depth_levels(update.get("depth"), side)
        self._record_large_order_events(side, levels)
        self._record_depth_imbalance_snapshot()
        self._save_latest(stream_name="depth_200")

    def _wait_for_reference_price(self) -> Optional[float]:
        deadline = time.time() + self.options_price_wait_seconds
        while not self.stop_event.is_set() and time.time() < deadline:
            price = self._current_ltp()
            if price is not None and price > 0:
                return price
            self._set_stream_state(
                "options_feed",
                status="waiting_for_primary_ltp",
                timeout_seconds=self.options_price_wait_seconds,
            )
            time.sleep(1)
        return self._current_ltp()

    def _resolve_option_instruments(self, reference_price: float) -> List[Dict[str, Any]]:
        instruments = self.reference.find_nearest_index_options(
            "NSE",
            "NIFTY",
            reference_price,
            strikes_each_side=self.options_strikes_each_side,
        )
        with self.lock:
            self.option_instruments_by_id = {
                str(item.get("security_id")): self._json_safe(item)
                for item in instruments
            }
        return instruments

    def _record_options_packet(self, packet: Dict[str, Any]) -> None:
        security_id = str(packet.get("security_id") or packet.get("securityId") or "")
        meta = self.option_instruments_by_id.get(security_id, {})
        best_bid, best_ask = self._best_bid_ask_from_packet(packet)
        payload = {
            "type": "options_full_packet",
            "security_id": security_id,
            "exchange_segment": packet.get("exchange_segment") or meta.get("exchange_segment") or "NSE_FNO",
            "display_name": meta.get("display_name"),
            "trading_symbol": meta.get("SEM_TRADING_SYMBOL") or meta.get("DISPLAY_NAME"),
            "expiry_date": meta.get("expiry_date"),
            "strike_price": self._first_number(meta, ("STRIKE_PRICE",)),
            "option_type": meta.get("OPTION_TYPE"),
            "latest_price": self._first_number(packet, ("last_price", "lastPrice", "ltp", "LTP", "latest_traded_price")),
            "last_traded_quantity": self._first_number(packet, ("last_traded_quantity", "lastTradedQuantity", "last_quantity", "LTQ")),
            "volume": self._first_number(packet, ("volume", "Volume", "total_volume")),
            "open_interest": self._first_number(packet, ("open_interest", "openInterest", "oi", "OI")),
            "oi_day_high": self._first_number(packet, ("oi_day_high", "oiDayHigh", "OI_day_high")),
            "oi_day_low": self._first_number(packet, ("oi_day_low", "oiDayLow", "OI_day_low")),
            "best_bid": best_bid,
            "best_ask": best_ask,
        }
        self._append_event("options_feed", payload, throttle=False)
        with self.lock:
            self.latest_option_packets[security_id] = payload
            self.metrics["options_packets_written"] += 1
            self.last_packet_at_utc_by_stream["options_feed"] = self._now_utc()
        self._set_stream_state("options_feed", status="receiving", last_packet_at_utc=self._now_utc())

    def _full_market_worker(self) -> None:
        stream_name = "full_market"
        while not self.stop_event.is_set():
            feed = None
            try:
                dhan = DhanService(self.config, prefer_gateway=False)
                self._wait_for_market_hours(stream_name)
                targets = self._ensure_targets()
                instrument = targets["primary_depth_instrument"]
                exchange = self._exchange_constant(MarketFeed, instrument.get("exchange_segment"))
                self._set_stream_state(
                    stream_name,
                    status="connecting",
                    security_id=instrument.get("security_id"),
                    exchange_segment=instrument.get("exchange_segment"),
                    sdk_exchange_code=exchange,
                )
                feed = MarketFeed(
                    dhan.dhan_context,
                    [(exchange, str(instrument["security_id"]), MarketFeed.Full)],
                    version="v2",
                )
                print(
                    "NIFTY full-market recorder connected for "
                    f"{instrument.get('display_name')} ({instrument['security_id']}) "
                    f"on {instrument.get('exchange_segment')}."
                )
                feed.run_forever()
                self._set_stream_state(stream_name, status="connected_waiting_for_first_packet")
                first_packet_seen = False
                while not self.stop_event.is_set() and self.market_time.is_market_hours():
                    try:
                        packet = feed.loop.run_until_complete(
                            asyncio.wait_for(
                                feed.get_instrument_data(),
                                timeout=self.first_packet_timeout_seconds,
                            )
                        )
                    except asyncio.TimeoutError:
                        if not first_packet_seen:
                            with self.lock:
                                self.metrics["no_packet_timeouts"] += 1
                            self._set_stream_state(
                                stream_name,
                                status="connected_but_no_packets",
                                timeout_seconds=self.first_packet_timeout_seconds,
                            )
                            raise TimeoutError(
                                f"{stream_name} received no packets within "
                                f"{self.first_packet_timeout_seconds}s after connect"
                            )
                        self._set_stream_state(stream_name, status="idle_after_packets")
                        continue
                    if isinstance(packet, dict):
                        first_packet_seen = True
                        self._record_full_packet(packet)
            except Exception as exc:
                self._record_error(stream_name, exc)
                time.sleep(self.reconnect_delay_seconds)
            finally:
                self._close_feed(feed)

    def _options_feed_worker(self) -> None:
        stream_name = "options_feed"
        if not self.options_feed_enabled:
            self._set_stream_state(stream_name, status="disabled")
            return

        while not self.stop_event.is_set():
            feed = None
            try:
                dhan = DhanService(self.config, prefer_gateway=False)
                self._wait_for_market_hours(stream_name)
                reference_price = self._wait_for_reference_price()
                if reference_price is None:
                    raise TimeoutError("Could not resolve NIFTY reference price for options feed.")

                instruments_meta = self._resolve_option_instruments(reference_price)
                if not instruments_meta:
                    raise RuntimeError("Could not resolve NIFTY option instruments from security_id_list.csv.")

                exchange = self._exchange_constant(MarketFeed, "NSE_FNO")
                instruments = [
                    (exchange, str(item["security_id"]), MarketFeed.Full)
                    for item in instruments_meta
                ]
                self._set_stream_state(
                    stream_name,
                    status="connecting",
                    reference_price=reference_price,
                    instrument_count=len(instruments),
                    strikes_each_side=self.options_strikes_each_side,
                    sdk_exchange_code=exchange,
                )
                feed = MarketFeed(dhan.dhan_context, instruments, version="v2")
                print(
                    "NIFTY options feed connected for "
                    f"{len(instruments)} contracts around reference {reference_price:.2f}."
                )
                feed.run_forever()
                self._set_stream_state(stream_name, status="connected_waiting_for_first_packet")
                first_packet_seen = False
                while not self.stop_event.is_set() and self.market_time.is_market_hours():
                    try:
                        packet = feed.loop.run_until_complete(
                            asyncio.wait_for(
                                feed.get_instrument_data(),
                                timeout=self.first_packet_timeout_seconds,
                            )
                        )
                    except asyncio.TimeoutError:
                        if not first_packet_seen:
                            with self.lock:
                                self.metrics["no_packet_timeouts"] += 1
                            self._set_stream_state(
                                stream_name,
                                status="connected_but_no_packets",
                                timeout_seconds=self.first_packet_timeout_seconds,
                            )
                            raise TimeoutError(
                                f"{stream_name} received no packets within "
                                f"{self.first_packet_timeout_seconds}s after connect"
                            )
                        self._set_stream_state(stream_name, status="idle_after_packets")
                        continue
                    if isinstance(packet, dict):
                        first_packet_seen = True
                        self._record_options_packet(packet)
                        self._save_latest(stream_name=stream_name)
            except Exception as exc:
                self._record_error(stream_name, exc)
                time.sleep(self.reconnect_delay_seconds)
            finally:
                self._close_feed(feed)

    def _depth_200_worker(self) -> None:
        stream_name = "depth_200"
        while not self.stop_event.is_set():
            feed = None
            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                dhan = DhanService(self.config, prefer_gateway=False)
                self._wait_for_market_hours(stream_name)
                targets = self._ensure_targets()
                instrument = targets["primary_depth_instrument"]
                exchange = self._exchange_constant(FullDepth, instrument.get("exchange_segment"))
                self._set_stream_state(
                    stream_name,
                    status="connecting",
                    security_id=instrument.get("security_id"),
                    exchange_segment=instrument.get("exchange_segment"),
                    sdk_exchange_code=exchange,
                )
                feed = FullDepth(
                    dhan.dhan_context,
                    [(exchange, str(instrument["security_id"]))],
                    depth_level=self.depth_level,
                )
                if self.depth_level == 200:
                    feed.ws_url = "wss://full-depth-api.dhan.co/twohundreddepth"
                print(
                    "NIFTY 200-depth recorder connected for "
                    f"{instrument.get('display_name')} ({instrument['security_id']}) "
                    f"on {instrument.get('exchange_segment')}."
                )
                print("NIFTY 200-depth WebSocket URL is hidden to avoid leaking the access token.")
                with redirect_stdout(StringIO()):
                    feed.run_forever()
                self._set_stream_state(stream_name, status="connected_waiting_for_first_packet")
                first_packet_seen = False
                while not self.stop_event.is_set() and self.market_time.is_market_hours():
                    try:
                        raw = feed.loop.run_until_complete(
                            asyncio.wait_for(
                                feed.ws.recv(),
                                timeout=self.first_packet_timeout_seconds,
                            )
                        )
                    except asyncio.TimeoutError:
                        if not first_packet_seen:
                            with self.lock:
                                self.metrics["no_packet_timeouts"] += 1
                            self._set_stream_state(
                                stream_name,
                                status="connected_but_no_packets",
                                timeout_seconds=self.first_packet_timeout_seconds,
                                likely_cause=(
                                    "silent or unsupported subscription; verify Dhan supports "
                                    f"{instrument.get('exchange_segment')} 200-depth for security "
                                    f"{instrument.get('security_id')}"
                                ),
                            )
                            raise TimeoutError(
                                f"{stream_name} received no packets within "
                                f"{self.first_packet_timeout_seconds}s after connect"
                            )
                        self._set_stream_state(stream_name, status="idle_after_packets")
                        continue
                    remaining_data = raw
                    while remaining_data:
                        update = feed.process_data(remaining_data)
                        if not update:
                            break
                        remaining_data = update.pop("remaining_data", None)
                        if update.get("type") in {"Bid", "Ask"}:
                            first_packet_seen = True
                            self._record_depth_packet(update)
            except Exception as exc:
                self._record_error(stream_name, exc)
                time.sleep(self.reconnect_delay_seconds)
            finally:
                self._close_feed(feed)
                if loop is not None:
                    try:
                        loop.close()
                    except Exception:
                        pass
                    try:
                        asyncio.set_event_loop(None)
                    except Exception:
                        pass

    def _start_workers(self) -> None:
        if self.started_threads:
            return
        self._ensure_targets()
        for name, target in (
            ("nifty-full-market", self._full_market_worker),
            ("nifty-depth-200", self._depth_200_worker),
            ("nifty-options-feed", self._options_feed_worker),
            ("nifty-depth-charts", self._chart_worker),
        ):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
        self.started_threads = True
        self._save_latest(status="started", force=True)

    def _chart_worker(self) -> None:
        stream_name = "chart_generator"
        if not self.charts_enabled:
            self._set_stream_state(stream_name, status="disabled")
            return

        while not self.stop_event.is_set():
            try:
                self._set_stream_state(stream_name, status="generating")
                bundle = self.charting.generate_for_market_date(self._market_date())
                with self.lock:
                    self.metrics["chart_generations"] += 1
                    self.last_packet_at_utc_by_stream[stream_name] = self._now_utc()
                self._set_stream_state(
                    stream_name,
                    status="ready" if bundle.get("generated") else "no_input_data",
                    chart_count=bundle.get("chart_count", 0),
                    latest_manifest=str(self.config.nifty_depth_charts_latest_path),
                )
            except Exception as exc:
                text = f"{type(exc).__name__}: {exc}"
                print(f"NIFTY depth chart generator error: {text}")
                with self.lock:
                    self.last_error_by_stream[stream_name] = text
                    self.metrics["chart_errors"] += 1
                self._set_stream_state(stream_name, status="error", last_error=text)
                try:
                    self._append_event(
                        "errors",
                        {"stream": stream_name, "error": text},
                        throttle=False,
                    )
                except Exception:
                    pass
            sleep_until = time.time() + self.chart_interval_seconds
            while not self.stop_event.is_set() and time.time() < sleep_until:
                time.sleep(1)

    def run(self) -> None:
        print("=" * 60)
        print("NIFTY MARKET STRUCTURE MONITOR")
        print("=" * 60)
        if not self.enabled:
            print("NIFTY depth monitor disabled via NIFTY_DEPTH_MONITOR_ENABLED=0.")
            self._save_latest(status="disabled", force=True)
            return

        while not self.stop_event.is_set():
            try:
                self._start_workers()
                status = "recording" if self.market_time.is_market_hours() else "waiting_for_market_open"
                self._save_latest(status=status, force=True)
                time.sleep(self.latest_save_interval_seconds)
            except Exception as exc:
                self._record_error("supervisor", exc)
                time.sleep(self.reconnect_delay_seconds)
