from __future__ import annotations

import asyncio
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
        self.raw_write_interval_seconds = self._env_float("NIFTY_DEPTH_RAW_WRITE_SECONDS", 1.0)
        self.first_packet_timeout_seconds = self._env_float("NIFTY_DEPTH_FIRST_PACKET_TIMEOUT_SECONDS", 20.0)
        self.max_latest_depth_levels = self._env_int("NIFTY_DEPTH_LATEST_LEVELS", 20)

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
        self.metrics = {
            "full_market_packets": 0,
            "depth_200_packets": 0,
            "depth_200_bid_packets": 0,
            "depth_200_ask_packets": 0,
            "raw_events_written": 0,
            "reconnects": 0,
            "no_packet_timeouts": 0,
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
        if throttle:
            last_write = self.last_raw_write_at.get(stream_name, 0.0)
            if now - last_write < self.raw_write_interval_seconds:
                return
            self.last_raw_write_at[stream_name] = now

        payload = dict(payload)
        payload.setdefault("captured_at_utc", self._now_utc())
        path = self._daily_dir() / f"{stream_name}.ndjson"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, default=str))
            handle.write("\n")
        with self.lock:
            self.metrics["raw_events_written"] += 1

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
                },
                "targets": self.targets,
                "metrics": dict(self.metrics),
                "stream_states": dict(self.stream_states),
                "last_packet_at_utc_by_stream": dict(self.last_packet_at_utc_by_stream),
                "last_error_by_stream": dict(self.last_error_by_stream),
                "latest_full_packet": self._build_full_packet_snapshot(),
                "latest_depth_200": self._build_depth_snapshot(),
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
            throttle=True,
        )
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
            throttle=True,
        )
        self._save_latest(stream_name="depth_200")

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
        ):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
        self.started_threads = True
        self._save_latest(status="started", force=True)

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
