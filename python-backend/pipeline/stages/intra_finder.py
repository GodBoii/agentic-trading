"""Full-universe live activity ranking and phase-aware setup detection."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from threading import RLock, Thread, current_thread
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

from pipeline.config import PipelineConfig
from pipeline.models import SetupEvent
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_calendar_service import MarketCalendarService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.process_memory_service import release_unused_process_memory
from pipeline.services.storage_service import StorageService
from pipeline.stages.activity_ranker import ActivityRanker, RankingResult
from pipeline.stages.live_state import InstrumentKey, LiveStockState
from pipeline.stages.setups import SetupEngine
from pipeline.stages.setups.base import SetupSignal


FEED_SEGMENTS = {1: "NSE_EQ", 4: "BSE_EQ"}


def subscription_batches(instruments: List[tuple], size: int = 100) -> List[List[tuple]]:
    if size <= 0:
        raise ValueError("subscription batch size must be positive")
    return [instruments[index : index + size] for index in range(0, len(instruments), size)]


class FeedIdleTimeout(RuntimeError):
    pass


class SessionEnded(RuntimeError):
    pass


class IntraFinder:
    EVENT_STATE_SCHEMA_VERSION = 7
    RUNTIME_STATE_SCHEMA_VERSION = 6

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config, prefer_gateway=False)
        self.historical_dhan = DhanService(self.config, prefer_gateway=True)
        self.market_time = MarketTimeService(self.config)
        self.market_calendar = MarketCalendarService(self.config)
        self.universe_payload: Dict[str, Any] = {}
        self.universe_version = ""
        self.universe_source_date = ""
        self.stocks: Dict[InstrumentKey, Dict[str, Any]] = {}
        self.states: Dict[InstrumentKey, LiveStockState] = {}
        self.security_index: Dict[int, List[InstrumentKey]] = defaultdict(list)
        self.event_state: Dict[str, Any] = {}
        self.ranker = ActivityRanker(
            hot_size=self.config.intra_finder_hot_set_size,
            reserve_size=self.config.intra_finder_hot_reserve_size,
            hysteresis_seconds=self.config.intra_finder_hot_hysteresis_seconds,
            max_packet_age_seconds=max(5, self.config.intra_finder_data_stale_seconds),
            max_trade_age_seconds=self.config.intra_finder_readiness_max_last_trade_age_seconds,
            max_spread_percent=self.config.intra_finder_max_spread_percent,
        )
        self.setup_engine = SetupEngine()
        self.last_rank_at = 0.0
        self.last_rank_duration_ms = 0.0
        self.last_ranking = RankingResult([], [], 0)
        self.raw_buffer: List[Dict[str, Any]] = []
        self.derived_buffer: List[Dict[str, Any]] = []
        self.last_flush = time.time()
        self.last_status_save = 0.0
        self.last_progress_log = 0.0
        self.progress_log_seconds = max(10, int(os.getenv("INTRA_FINDER_PROGRESS_LOG_SECONDS", "60")))
        self.io_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="intra-io")
        self.io_futures: set[Future] = set()
        self.recovery_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="intra-recovery")
        self.recovery_futures: set[Future] = set()
        self.coverage_verification_future: Optional[Future] = None
        self.opening_recovery_requested: set[InstrumentKey] = set()
        self.opening_range_recovery_completed = 0
        self.opening_range_recovery_failed = 0
        self.state_lock = RLock()
        self.dispatch_lock = RLock()
        self.agent_threads: set[Thread] = set()
        self.current_feed: Any = None
        self.last_global_packet_at: Optional[datetime] = None
        self.connected_at: Optional[datetime] = None
        self.connection_state = "STARTING"
        self.session_state = "STARTING"
        self.last_connection_error: Optional[str] = None
        self.released_session_date: Optional[str] = None
        self.connection_generation = 0
        self.packet_count = 0
        self.reconnect_count = 0
        self.universe_wait_count = 0
        self.candidates_seen = 0
        self.events_formed = 0
        self.events_triggered = 0
        self.events_suppressed = 0
        self.agent_dispatch_successes = 0
        self.agent_dispatch_failures = 0
        self.gate_failure_counts: Counter[str] = Counter()
        self.received_keys: set[InstrumentKey] = set()
        self.full_packet_keys: set[InstrumentKey] = set()
        self.quote_verified_keys: set[InstrumentKey] = set()
        self.coverage_milestones_logged: set[int] = set()
        self.detector_mode = "cross_sectional_setups_v2"
        self.shadow_mode = _env_bool(
            "INTRA_FINDER_SHADOW_MODE", self.config.intra_finder_shadow_mode
        )
        self.record_all_raw = _env_bool(
            "INTRA_FINDER_RECORD_ALL_RAW_PACKETS",
            self.config.intra_finder_record_all_raw_packets,
        )
        self.record_hot_raw = _env_bool(
            "INTRA_FINDER_RECORD_HOT_RAW_PACKETS",
            self.config.intra_finder_record_hot_raw_packets,
        )

    def _log(self, message: str) -> None:
        print(
            f"[{self.market_time.now().strftime('%Y-%m-%d %H:%M:%S %Z')}] "
            f"[Intra-Finder] {message}",
            flush=True,
        )

    @staticmethod
    def _key(stock: Dict[str, Any]) -> InstrumentKey:
        return str(stock["exchange_segment"]).upper(), int(stock["security_id"])

    @staticmethod
    def _key_text(key: InstrumentKey) -> str:
        return f"{key[0]}|{key[1]}"

    @staticmethod
    def _parse_key(value: str) -> Optional[InstrumentKey]:
        try:
            segment, security_id = value.split("|", 1)
            return segment.upper(), int(security_id)
        except (AttributeError, TypeError, ValueError):
            return None

    def load_universe(self) -> List[Dict[str, Any]]:
        payload = StorageService.load_snapshot(self.config.stage1_latest_path)
        if not payload or payload.get("stage") != "universe_scanner":
            raise FileNotFoundError("A successful Universe Scanner snapshot is not available.")
        summary = payload.get("summary") or {}
        if summary.get("status") != "completed":
            raise RuntimeError("Universe Scanner output is degraded.")
        source_date = str(summary.get("market_date") or "")
        try:
            age_days = (
                date.fromisoformat(self.market_time.market_date_str())
                - date.fromisoformat(source_date)
            ).days
        except ValueError as exc:
            raise RuntimeError("Universe Scanner market date is invalid.") from exc
        if age_days < 0 or age_days > self.config.stage1_universe_fallback_max_age_days:
            raise RuntimeError("Universe Scanner output is too old for fallback use.")
        stocks = [stock for stock in payload.get("stocks") or [] if isinstance(stock, dict)]
        if not stocks:
            raise RuntimeError("Universe Scanner returned no stocks.")
        new_stocks = {self._key(stock): stock for stock in stocks}
        if len(new_stocks) != len(stocks):
            raise RuntimeError("Universe Scanner produced duplicate venue identities.")
        if len(new_stocks) > 5_000:
            raise RuntimeError("The equity universe exceeds one Dhan feed connection.")
        same_universe = self.universe_version == str(summary.get("universe_version") or "") and set(self.stocks) == set(new_stocks)
        self.universe_payload = payload
        self.universe_version = str(summary.get("universe_version") or source_date)
        self.universe_source_date = source_date
        self.stocks = new_stocks
        self.security_index = defaultdict(list)
        for key in new_stocks:
            self.security_index[key[1]].append(key)
        if not same_universe or not self.states:
            old_states = self.states
            self.states = {
                key: old_states.get(key) or LiveStockState.from_stock(stock)
                for key, stock in new_stocks.items()
            }
            market_date = self.market_time.market_date_str()
            self._restore_runtime_state(market_date)
            self._load_event_state(market_date)
        return stocks

    def _load_event_state(self, market_date: str) -> None:
        loaded = StorageService.load_snapshot(self.config.stage2_event_state_path(market_date)) or {}
        if (
            int(loaded.get("schema_version") or 0) == self.EVENT_STATE_SCHEMA_VERSION
            and loaded.get("universe_version") == self.universe_version
        ):
            self.event_state = loaded
            return
        self.event_state = {
            "schema_version": self.EVENT_STATE_SCHEMA_VERSION,
            "universe_version": self.universe_version,
            "events": {},
        }
        StorageService.save_snapshot(self.config.stage2_event_state_path(market_date), self.event_state)

    def _runtime_state_payload(self, market_date: Optional[str] = None) -> Dict[str, Any]:
        state_rows: Dict[str, Any] = {}
        with self.state_lock:
            for key, state in self.states.items():
                payload = state.checkpoint()
                if not state.is_hot:
                    payload["price_samples"] = payload["price_samples"][-30:]
                    payload["value_samples"] = payload["value_samples"][-30:]
                    payload["depth_samples"] = payload["depth_samples"][-10:]
                    payload["minute_bars"] = payload["minute_bars"][-20:]
                state_rows[self._key_text(key)] = payload
        return {
            "schema_version": self.RUNTIME_STATE_SCHEMA_VERSION,
            "market_date": market_date or self.market_time.market_date_str(),
            "universe_version": self.universe_version,
            "saved_at": self.market_time.now().isoformat(),
            "states": state_rows,
        }

    def _restore_runtime_state(self, market_date: str) -> None:
        payload = StorageService.load_snapshot(self.config.stage2_runtime_state_path(market_date))
        if (
            not payload
            or payload.get("market_date") != market_date
            or payload.get("universe_version") != self.universe_version
            or int(payload.get("schema_version") or 0) != self.RUNTIME_STATE_SCHEMA_VERSION
        ):
            return
        restored = 0
        for raw_key, saved in (payload.get("states") or {}).items():
            key = self._parse_key(raw_key)
            state = self.states.get(key) if key else None
            if state is not None and isinstance(saved, dict):
                state.restore(saved)
                restored += 1
        if restored:
            self._log(f"Restored current-session state for {restored:,} instruments.")

    @staticmethod
    def _feed_exchange(stock: Dict[str, Any]) -> Any:
        from dhanhq import MarketFeed

        segment = str(stock.get("exchange_segment") or "").upper()
        if segment == "NSE_EQ":
            return MarketFeed.NSE
        if segment == "BSE_EQ":
            return MarketFeed.BSE
        raise ValueError(f"Unsupported equity segment: {segment}")

    def build_instruments(self, stocks: Iterable[Dict[str, Any]]) -> List[tuple]:
        from dhanhq import MarketFeed

        instruments = [
            (self._feed_exchange(stock), str(stock["security_id"]), MarketFeed.Full)
            for stock in stocks
        ]
        if len(instruments) > 5_000:
            raise RuntimeError(f"Intra-Finder universe has {len(instruments)} instruments; maximum is 5000.")
        return instruments

    def _packet_key(self, packet: Dict[str, Any]) -> Optional[InstrumentKey]:
        try:
            security_id = int(packet.get("security_id"))
        except (TypeError, ValueError):
            return None
        raw_segment = packet.get("exchange_segment")
        if isinstance(raw_segment, str) and raw_segment.upper() in {"NSE_EQ", "BSE_EQ"}:
            segment = raw_segment.upper()
        else:
            try:
                segment = FEED_SEGMENTS.get(int(raw_segment))
            except (TypeError, ValueError):
                segment = None
        if segment:
            key = segment, security_id
            return key if key in self.stocks else None
        candidates = self.security_index.get(security_id) or []
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _number(payload: Dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            try:
                if payload.get(key) not in (None, ""):
                    value = float(payload[key])
                    return value if value == value else None
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _depth(packet: Dict[str, Any]) -> List[Dict[str, float]]:
        result: List[Dict[str, float]] = []
        for row in packet.get("depth") or []:
            if not isinstance(row, dict):
                continue
            parsed: Dict[str, float] = {}
            for key in ("bid_price", "ask_price", "bid_quantity", "ask_quantity", "bid_orders", "ask_orders"):
                try:
                    parsed[key] = float(row.get(key) or 0.0)
                except (TypeError, ValueError):
                    parsed[key] = 0.0
            result.append(parsed)
        return result[:5]

    @staticmethod
    def _depth_features(depth: List[Dict[str, float]], price: float) -> Dict[str, Any]:
        bids = sum(row["bid_quantity"] for row in depth)
        asks = sum(row["ask_quantity"] for row in depth)
        bid_orders = sum(row["bid_orders"] for row in depth)
        ask_orders = sum(row["ask_orders"] for row in depth)
        best_bid = max((row["bid_price"] for row in depth if row["bid_price"] > 0), default=0.0)
        best_ask = min((row["ask_price"] for row in depth if row["ask_price"] > 0), default=0.0)
        spread = (best_ask - best_bid) / price * 100 if price > 0 and best_ask >= best_bid > 0 else None
        return {
            "best_bid": best_bid or None,
            "best_ask": best_ask or None,
            "spread_percent": round(spread, 5) if spread is not None else None,
            "bid_quantity_5": bids,
            "ask_quantity_5": asks,
            "depth_imbalance": (bids - asks) / (bids + asks) if bids + asks > 0 else 0.0,
            "order_count_imbalance": (
                (bid_orders - ask_orders) / (bid_orders + ask_orders)
                if bid_orders + ask_orders > 0
                else 0.0
            ),
        }

    @staticmethod
    def _packet_last_trade_at(packet: Dict[str, Any], received_at: datetime) -> Optional[datetime]:
        raw = packet.get("LTT") or packet.get("last_trade_time") or packet.get("last_traded_time")
        if raw in (None, ""):
            return None
        text = str(raw).strip()
        try:
            value = datetime.fromisoformat(text)
            if value.tzinfo is None:
                value = value.replace(tzinfo=received_at.tzinfo)
            return value.astimezone(received_at.tzinfo) if received_at.tzinfo else value
        except ValueError:
            pass
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                value = datetime.strptime(text, pattern).time()
            except ValueError:
                continue
            return received_at.replace(hour=value.hour, minute=value.minute, second=value.second, microsecond=0)
        return None

    @staticmethod
    def _estimated_slippage(
        depth: List[Dict[str, float]],
        *,
        direction: str,
        reference_price: float,
        trade_amount: float,
    ) -> Optional[float]:
        if reference_price <= 0 or trade_amount <= 0:
            return None
        quantity = trade_amount / reference_price
        price_key = "ask_price" if direction == "LONG" else "bid_price"
        quantity_key = "ask_quantity" if direction == "LONG" else "bid_quantity"
        remaining, cost, filled = quantity, 0.0, 0.0
        for row in depth:
            available = max(0.0, row.get(quantity_key, 0.0))
            level_price = max(0.0, row.get(price_key, 0.0))
            take = min(remaining, available)
            if take > 0 and level_price > 0:
                cost += take * level_price
                filled += take
                remaining -= take
            if remaining <= 0:
                break
        if filled < quantity or filled <= 0:
            return None
        return abs(cost / filled - reference_price) / reference_price * 100.0

    def process_packet(
        self,
        packet: Dict[str, Any],
        *,
        received_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        received_at = received_at or self.market_time.now()
        key = self._packet_key(packet)
        state = self.states.get(key) if key else None
        stock = self.stocks.get(key) if key else None
        price = self._number(packet, "LTP", "ltp", "last_price", "latest_traded_price")
        if key is None or state is None or stock is None:
            return None
        self.packet_count += 1
        self.last_global_packet_at = received_at
        self.received_keys.add(key)
        self._log_coverage_milestones()
        if price is None or price <= 0:
            self._flush_if_due()
            return None
        previous_close = self._number(packet, "close", "previous_close", "prev_close")
        if previous_close is not None and previous_close > 0 and received_at.time() < dt_time(15, 30):
            state.previous_close = previous_close
        volume = self._number(packet, "volume", "total_volume")
        if volume is None:
            volume = state.cumulative_volume
        vwap = self._number(packet, "avg_price", "average_price", "ATP")
        depth = self._depth(packet)
        state.apply_packet(
            received_at=received_at,
            price=price,
            cumulative_volume=volume,
            vwap=vwap,
            last_trade_at=self._packet_last_trade_at(packet, received_at),
            last_trade_quantity=self._number(packet, "LTQ", "last_trade_quantity"),
            depth=depth,
            depth_features=self._depth_features(depth, price),
        )
        if received_at.time() < dt_time(9, 15):
            state.session_open = None
            state.session_high = None
            state.session_low = None
        else:
            official_open = self._number(packet, "open", "day_open")
            official_high = self._number(packet, "high", "day_high")
            official_low = self._number(packet, "low", "day_low")
            if official_open and official_open > 0:
                state.session_open = official_open
            if official_high and official_high > 0:
                state.session_high = max(state.session_high or official_high, official_high)
            if official_low and official_low > 0:
                state.session_low = min(state.session_low or official_low, official_low)
        self.full_packet_keys.add(key)
        self._rank_if_due(received_at)
        self._record_observation(state, packet, received_at)
        emitted: Optional[Dict[str, Any]] = None
        if (
            state.is_hot
            and state.activity_rank is not None
            and state.activity_rank <= self.config.intra_finder_setup_rank_limit
        ):
            signals = self.setup_engine.evaluate(state, received_at)
            self.candidates_seen += len(signals)
            for signal in sorted(signals, key=_signal_priority):
                failures, slippage = self._safety_gates(state, signal, received_at)
                if failures:
                    self.gate_failure_counts.update(failures)
                    self.events_suppressed += 1
                    continue
                emitted = self._create_event(stock, state, signal, slippage, received_at)
                if emitted is not None:
                    break
        self._flush_if_due()
        self._save_status_if_due()
        return emitted

    def _rank_if_due(self, now: datetime) -> None:
        interval = (
            self.config.intra_finder_open_rank_interval_seconds
            if dt_time(9, 15) <= now.time() < dt_time(9, 30)
            else self.config.intra_finder_rank_interval_seconds
        )
        if now.timestamp() - self.last_rank_at < interval:
            return
        started = time.perf_counter()
        self.last_ranking = self.ranker.rank(self.states, now)
        self.last_rank_at = now.timestamp()
        self.last_rank_duration_ms = (time.perf_counter() - started) * 1000.0

    def _safety_gates(
        self,
        state: LiveStockState,
        signal: SetupSignal,
        now: datetime,
    ) -> Tuple[List[str], Optional[float]]:
        failures: List[str] = []
        if signal.expires_at <= now:
            failures.append("EVENT_EXPIRED")
        if len(state.depth) < 5:
            failures.append("DEPTH_INCOMPLETE")
        if state.spread_percent is None or state.spread_percent > self.config.intra_finder_max_spread_percent:
            failures.append("SPREAD_TOO_WIDE")
        if not self.connected_at or (
            now - self.connected_at
        ).total_seconds() < self.config.intra_finder_reconnect_warmup_seconds:
            failures.append("CONNECTION_WARMING_UP")
        if now.time() >= dt_time(15, 0):
            failures.append("ENTRY_CUTOFF")
        if signal.direction == "LONG" and state.upper_circuit and state.latest_price >= state.upper_circuit * 0.998:
            failures.append("UPPER_CIRCUIT_PROXIMITY")
        if signal.direction == "SHORT" and state.lower_circuit and state.latest_price <= state.lower_circuit * 1.002:
            failures.append("LOWER_CIRCUIT_PROXIMITY")
        if signal.family == "GAP_REJECTION" and (state.corporate_action or {}).get("gap_setup_disabled"):
            failures.append("CORPORATE_ACTION_GAP_UNTRUSTED")
        slippage = self._estimated_slippage(
            state.depth,
            direction=signal.direction,
            reference_price=state.latest_price,
            trade_amount=state.latest_price,
        )
        if slippage is None or slippage > self.config.intra_finder_max_slippage_percent:
            failures.append("INSUFFICIENT_DEPTH_CAPACITY")
        return failures, slippage

    def _create_event(
        self,
        stock: Dict[str, Any],
        state: LiveStockState,
        signal: SetupSignal,
        slippage: Optional[float],
        now: datetime,
    ) -> Optional[Dict[str, Any]]:
        identity = "|".join(
            (
                self.market_time.market_date_str(), state.exchange_segment,
                str(state.security_id), signal.family, signal.direction,
                signal.armed_at.isoformat(),
            )
        )
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        if event_id in (self.event_state.get("events") or {}):
            self.events_suppressed += 1
            return None
        features = state.feature_snapshot(now)
        bars = [asdict(bar) for bar in list(state.minute_bars)[-20:]]
        price = state.latest_price
        event = SetupEvent(
            event_id=event_id,
            market_date=self.market_time.market_date_str(),
            universe_version=self.universe_version,
            isin=state.isin,
            exchange_segment=state.exchange_segment,
            security_id=state.security_id,
            symbol=state.symbol,
            direction=signal.direction,
            setup_type=signal.family,
            setup_state="TRIGGERED",
            setup_score=round(state.hotness, 2),
            payload={
                "display_name": stock.get("display_name"),
                "instrument": stock.get("instrument", "EQUITY"),
                "created_at": now.isoformat(),
                "armed_at": signal.armed_at.isoformat(),
                "triggered_at": signal.triggered_at.isoformat(),
                "expires_at": signal.expires_at.isoformat(),
                "price": price,
                "trigger_price": signal.trigger_price,
                "trigger_level": signal.trigger_level,
                "entry_zone": [round(price * 0.9995, 4), round(price * 1.0005, 4)],
                "invalidation_level": signal.invalidation_price,
                "reason_for_attention": signal.reason,
                "setup_diagnostics": signal.diagnostics,
                "activity": {
                    "rank": state.activity_rank,
                    "hotness": round(state.hotness, 4),
                    "volume_pace": state.volume_pace,
                    "volume_percentile": state.volume_percentile,
                    "realized_volatility_percent": state.realized_volatility_percent,
                    "volatility_percentile": state.volatility_percentile,
                    "traded_value_5m": state.traded_value_5m,
                    "traded_value_percentile": state.value_percentile,
                    "trend_efficiency": state.trend_efficiency,
                    "market_return_5m_percent": state.market_return_5m_percent,
                    "relative_strength_5m_percent": state.relative_strength_5m_percent,
                    "relative_strength_percentile": state.relative_strength_percentile,
                },
                "historical": stock.get("historical"),
                "intraday_baseline_status": (stock.get("intraday_baselines") or {}).get("status"),
                "corporate_action": state.corporate_action,
                "opening_range": {
                    "high": state.opening_range_high,
                    "low": state.opening_range_low,
                    "complete": state.opening_range_complete,
                },
                "vwap": state.session_vwap,
                "relative_volume": state.volume_pace,
                "volume_acceleration": state.volume_acceleration,
                "spread": state.spread_percent,
                "five_level_depth": list(state.depth),
                "five_level_depth_summary": {
                    "best_bid": state.best_bid,
                    "best_ask": state.best_ask,
                    "bid_quantity": state.bid_quantity_5,
                    "ask_quantity": state.ask_quantity_5,
                    "imbalance": state.depth_imbalance,
                    "persistent_imbalance_30s": features.get("depth_imbalance_median_30s"),
                },
                "estimated_slippage": slippage,
                "recent_closed_bars": bars[-10:],
                "chart_seed_bars": bars,
                "detector_mode": self.detector_mode,
                "detector_schema_version": self.EVENT_STATE_SCHEMA_VERSION,
                "universe_source_date": self.universe_source_date,
                "latest_nifty_context": self._load_context(self.config.nifty_depth_latest_path),
                "shadow_mode": self.shadow_mode,
            },
        ).as_dict()
        self.event_state.setdefault("events", {})[event_id] = {
            "created_at": now.isoformat(),
            "expires_at": signal.expires_at.isoformat(),
            "instrument": self._key_text(state.key),
            "setup_type": signal.family,
            "direction": signal.direction,
        }
        self.events_formed += 1
        event_state_snapshot = {
            **self.event_state,
            "events": dict(self.event_state.get("events") or {}),
        }
        self._submit_io(self._persist_event, event, event_state_snapshot)
        if not self.shadow_mode:
            self._dispatch_event(event)
        self._log(
            f"TRIGGER | {state.symbol} {signal.direction} {signal.family} "
            f"rank={state.activity_rank} hotness={state.hotness:.1f} price={price:.2f}"
        )
        return event

    def _persist_event(self, event: Dict[str, Any], event_state: Dict[str, Any]) -> None:
        market_date = str(event["market_date"])
        StorageService.save_snapshot(self.config.stage2_event_state_path(market_date), event_state)
        StorageService.append_json_line(self.config.stage2_events_path(market_date), event)

    def _dispatch_event(self, event: Dict[str, Any]) -> bool:
        with self.dispatch_lock:
            self.agent_threads = {thread for thread in self.agent_threads if thread.is_alive()}
            if len(self.agent_threads) >= self.config.intra_finder_max_dispatch_concurrency:
                self.events_suppressed += 1
                self.gate_failure_counts.update(["AGENT_DISPATCH_CAPACITY"])
                return False
            event_id = str(event.get("event_id") or uuid.uuid4().hex[:12])
            thread = Thread(
                target=self._post_agent_event_immediately,
                args=(event,),
                name=f"intra-agent-dispatch-{event_id[:12]}",
                daemon=True,
            )
            self.agent_threads.add(thread)
            self.events_triggered += 1
        try:
            thread.start()
        except Exception:
            with self.dispatch_lock:
                self.agent_threads.discard(thread)
                self.agent_dispatch_failures += 1
            raise
        return True

    def _post_agent_event_immediately(self, event: Dict[str, Any]) -> None:
        try:
            if event.get("expires_at"):
                expires_at = datetime.fromisoformat(str(event["expires_at"]))
                if self.market_time.now() >= expires_at:
                    raise TimeoutError("event_expired_before_dispatch")
            self._post_agent_event(event)
            with self.dispatch_lock:
                self.agent_dispatch_successes = getattr(self, "agent_dispatch_successes", 0) + 1
        except Exception as exc:
            with self.dispatch_lock:
                self.agent_dispatch_failures = getattr(self, "agent_dispatch_failures", 0) + 1
            if hasattr(self, "market_time"):
                self._log(f"Agent dispatch failed: {type(exc).__name__}.")
        finally:
            with self.dispatch_lock:
                self.agent_threads.discard(current_thread())

    @staticmethod
    def _post_agent_event(event: Dict[str, Any]) -> None:
        endpoint = os.getenv("AI_TRADING_EVENT_URL", "http://ai-trading-agents:8020/ai-trading/event")
        headers = {"Content-Type": "application/json"}
        token = os.getenv("AI_TRADING_BACKEND_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.post(endpoint, json=event, headers=headers, timeout=10)
        response.raise_for_status()

    def _record_observation(
        self,
        state: LiveStockState,
        packet: Dict[str, Any],
        received_at: datetime,
    ) -> None:
        second = int(received_at.timestamp())
        if self.record_all_raw or (self.record_hot_raw and state.is_hot):
            self.raw_buffer.append(
                {
                    "received_at": received_at.isoformat(),
                    "security_id": state.security_id,
                    "exchange_segment": state.exchange_segment,
                    "packet_json": json.dumps(packet, separators=(",", ":"), default=str),
                    "capture_scope": "all" if self.record_all_raw else "hot_only",
                }
            )
        if state.last_recorded_second == second:
            return
        state.last_recorded_second = second
        features = state.feature_snapshot(received_at)
        features.pop("corporate_action", None)
        self.derived_buffer.append(
            {
                "received_at": received_at.replace(microsecond=0).isoformat(),
                "security_id": state.security_id,
                "exchange_segment": state.exchange_segment,
                "symbol": state.symbol,
                **features,
            }
        )

    def _log_coverage_milestones(self) -> None:
        expected = len(self.stocks)
        if not expected:
            return
        percent = int(len(self.received_keys) * 100 / expected)
        for milestone in (25, 50, 75, 90, 100):
            if percent >= milestone and milestone not in self.coverage_milestones_logged:
                self.coverage_milestones_logged.add(milestone)
                self._log(f"Feed coverage reached {milestone}%: {len(self.received_keys):,}/{expected:,}.")

    def _fetch_opening_range(
        self, stock: Dict[str, Any]
    ) -> Tuple[InstrumentKey, Optional[float], Optional[float], Optional[str]]:
        key = self._key(stock)
        try:
            response = self.historical_dhan.fetch_intraday_history(
                key[1], days=1, interval=1, retries=2,
                exchange_segment=key[0], instrument_candidates=["EQUITY"],
            )
            if not response or str(response.get("status") or "").lower() != "success":
                return key, None, None, "historical_request_failed"
            frame = self.historical_dhan.intraday_response_to_df(response)
            if frame.empty:
                return key, None, None, "historical_response_empty"
            timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
            frame["timestamp"] = timestamps.dt.tz_convert(self.market_time.tz)
            opening = frame[
                (frame["timestamp"].dt.date == self.market_time.now().date())
                & (frame["timestamp"].dt.time >= dt_time(9, 15))
                & (frame["timestamp"].dt.time < dt_time(9, 30))
            ].copy()
            if opening["timestamp"].dt.floor("min").nunique() < 12:
                return key, None, None, "opening_range_incomplete"
            return key, float(opening["high"].max()), float(opening["low"].min()), None
        except Exception as exc:
            return key, None, None, type(exc).__name__

    def _apply_opening_range_recovery(self, future: Future) -> None:
        try:
            key, high, low, error = future.result()
        except Exception:
            self.opening_range_recovery_failed += 1
            return
        state = self.states.get(key)
        if state is None or error or high is None or low is None:
            self.opening_range_recovery_failed += 1
            return
        if not state.opening_range_complete:
            state.opening_range_high = high
            state.opening_range_low = low
            state.opening_range_complete = True
            state.opening_range_source = "historical_recovery"
        self.opening_range_recovery_completed += 1

    def _start_opening_range_recovery(self) -> None:
        if self.market_time.now().time() < dt_time(9, 30):
            return
        self.recovery_futures = {future for future in self.recovery_futures if not future.done()}
        capacity = max(0, 100 - len(self.recovery_futures))
        if capacity <= 0:
            return
        missing = [
            (key, stock)
            for key, stock in self.stocks.items()
            if not self.states[key].opening_range_complete and key not in self.opening_recovery_requested
        ][:capacity]
        for key, stock in missing:
            self.opening_recovery_requested.add(key)
            future = self.recovery_executor.submit(self._fetch_opening_range, stock)
            self.recovery_futures.add(future)
            future.add_done_callback(self._apply_opening_range_recovery)

    def _verify_unobserved(self, keys: List[InstrumentKey]) -> set[InstrumentKey]:
        verified: set[InstrumentKey] = set()
        by_segment: Dict[str, List[int]] = defaultdict(list)
        for segment, security_id in keys:
            by_segment[segment].append(security_id)
        for segment, security_ids in by_segment.items():
            for batch in subscription_batches(security_ids, size=1000):
                quotes = self.historical_dhan.fetch_quote_batch(batch, exchange_segment=segment)
                for security_id, quote in quotes.items():
                    if self._number(quote, "last_price", "LTP", "ltp"):
                        verified.add((segment, int(security_id)))
        return verified

    def _start_coverage_verification(self) -> None:
        if not self.connected_at:
            return
        if (self.market_time.now() - self.connected_at).total_seconds() < self.config.intra_finder_subscription_verify_seconds:
            return
        if self.coverage_verification_future and not self.coverage_verification_future.done():
            return
        missing = list(set(self.stocks) - self.received_keys)
        if not missing:
            return
        future = self.recovery_executor.submit(self._verify_unobserved, missing)
        self.coverage_verification_future = future

        def apply(completed: Future) -> None:
            try:
                self.quote_verified_keys.update(completed.result())
            except Exception:
                return

        future.add_done_callback(apply)

    def _load_context(self, path: Path) -> Optional[Dict[str, Any]]:
        payload = StorageService.load_snapshot(path)
        if not isinstance(payload, dict):
            return None
        return {
            "stage": payload.get("stage"),
            "generated_at_utc": payload.get("generated_at_utc"),
            "summary": payload.get("summary"),
            "derived_signals": payload.get("derived_signals"),
        }

    def _write_parquet(self, directory: Path, prefix: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.parquet"
        pd.DataFrame(rows).to_parquet(path, index=False, compression="zstd")

    def _submit_io(self, function: Any, *args: Any) -> None:
        self.io_futures = {future for future in self.io_futures if not future.done()}
        self.io_futures.add(self.io_executor.submit(function, *args))

    def _persist_buffers(
        self,
        raw: List[Dict[str, Any]],
        derived: List[Dict[str, Any]],
        checkpoint: Dict[str, Any],
        market_date: str,
    ) -> None:
        base = self.config.stage2_results_dir / market_date
        for rows, directory_name, prefix in (
            (raw, "raw-depth", "packets"),
            (derived, "one-second", "snapshots"),
        ):
            grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in rows:
                hour = datetime.fromisoformat(str(row["received_at"])).strftime("%H")
                grouped[hour].append(row)
            for hour, hour_rows in grouped.items():
                self._write_parquet(base / directory_name / f"hour={hour}", prefix, hour_rows)
        StorageService.save_snapshot(self.config.stage2_runtime_state_path(market_date), checkpoint)

    def flush(
        self,
        *,
        force_checkpoint: bool = False,
        checkpoint_market_date: Optional[str] = None,
    ) -> None:
        if not self.raw_buffer and not self.derived_buffer and not force_checkpoint:
            return
        raw, derived = self.raw_buffer, self.derived_buffer
        self.raw_buffer, self.derived_buffer = [], []
        market_date = checkpoint_market_date or self.market_time.market_date_str()
        self._submit_io(
            self._persist_buffers,
            raw,
            derived,
            self._runtime_state_payload(market_date),
            market_date,
        )
        self.last_flush = time.time()

    def _flush_if_due(self) -> None:
        if time.time() - self.last_flush >= self.config.intra_finder_flush_seconds:
            self.flush()

    def _save_status_if_due(self, *, force: bool = False) -> None:
        if not force and time.time() - self.last_status_save < self.config.intra_finder_status_seconds:
            return
        now = self.market_time.now()
        stale_before = now - timedelta(seconds=self.config.intra_finder_data_stale_seconds)
        stock_rows: List[Dict[str, Any]] = []
        stale = 0
        for key, state in self.states.items():
            try:
                packet_at = datetime.fromisoformat(str(state.last_packet_at))
            except (TypeError, ValueError):
                packet_at = None
            if packet_at is None or packet_at < stale_before:
                stale += 1
                state.status = "DATA_STALE" if packet_at else "WAITING_FOR_DATA"
            stock_rows.append(
                {
                    "security_id": key[1],
                    "exchange_segment": key[0],
                    "symbol": state.symbol,
                    "state": state.status,
                    "last_packet_at": state.last_packet_at,
                    "features": state.feature_snapshot(now),
                }
            )
        global_age = (
            max(0.0, (now - self.last_global_packet_at).total_seconds())
            if self.last_global_packet_at
            else None
        )
        summary = {
            "status": (
                "recording"
                if self.connection_state == "CONNECTED"
                and (global_age is None or global_age <= self.config.intra_finder_global_idle_seconds)
                else "degraded"
            ),
            "market_date": self.market_time.market_date_str(),
            "universe_version": self.universe_version,
            "universe_source_date": self.universe_source_date,
            "expected_instruments": len(self.stocks),
            "requested_instruments": len(self.stocks),
            "subscribed_instruments": len(self.received_keys),
            "observed_instruments": len(self.received_keys),
            "full_packet_instruments": len(self.full_packet_keys),
            "quote_verified_instruments": len(self.quote_verified_keys),
            "covered_instruments": len(self.received_keys | self.quote_verified_keys),
            "active_instruments": len(self.states) - stale,
            "stale_instruments": stale,
            "packet_count": self.packet_count,
            "connection_state": self.connection_state,
            "session_state": self.session_state,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_global_packet_at": self.last_global_packet_at.isoformat() if self.last_global_packet_at else None,
            "global_packet_age_seconds": round(global_age, 3) if global_age is not None else None,
            "reconnect_count": self.reconnect_count,
            "universe_wait_count": self.universe_wait_count,
            "opening_range_complete": sum(state.opening_range_complete for state in self.states.values()),
            "opening_range_recovery": {
                "requested": len(self.opening_recovery_requested),
                "completed": self.opening_range_recovery_completed,
                "failed": self.opening_range_recovery_failed,
            },
            "rvol_available": sum(state.volume_pace is not None for state in self.states.values()),
            "detector_mode": self.detector_mode,
            "rank_eligible": self.last_ranking.eligible_count,
            "hot_instruments": len(self.last_ranking.hot),
            "rank_duration_ms": round(self.last_rank_duration_ms, 3),
            "candidates_seen": self.candidates_seen,
            "events_formed": self.events_formed,
            "events_triggered": self.events_triggered,
            "events_suppressed": self.events_suppressed,
            "agent_dispatch_active": len(self.agent_threads),
            "agent_dispatch_successes": self.agent_dispatch_successes,
            "agent_dispatch_failures": self.agent_dispatch_failures,
            "gate_failure_counts": dict(self.gate_failure_counts),
            "shadow_mode": self.shadow_mode,
            "raw_capture_scope": "all" if self.record_all_raw else "hot_only" if self.record_hot_raw else "disabled",
        }
        payload = StorageService.build_payload("intra_finder", summary, "stocks", stock_rows)
        self._submit_io(self._persist_status, payload)
        self.last_status_save = time.time()
        self._log_progress(summary, force=force)

    def _log_progress(self, summary: Dict[str, Any], *, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.last_progress_log < self.progress_log_seconds:
            return
        common_gates = ", ".join(
            f"{name}={count}" for name, count in self.gate_failure_counts.most_common(4)
        ) or "none"
        self._log(
            f"LIVE | connection={summary['connection_state']} packets={summary['packet_count']:,} "
            f"coverage={summary['observed_instruments']:,}/{summary['expected_instruments']:,} "
            f"eligible={summary['rank_eligible']:,} hot={summary['hot_instruments']:,} "
            f"rank_ms={summary['rank_duration_ms']:.2f} candidates={summary['candidates_seen']:,} "
            f"events={summary['events_formed']:,} agents={summary['agent_dispatch_active']:,} "
            f"shadow={summary['shadow_mode']} gates={common_gates}"
        )
        self.last_progress_log = now

    def _persist_status(self, payload: Dict[str, Any]) -> None:
        market_date = str((payload.get("summary") or {}).get("market_date") or self.market_time.market_date_str())
        StorageService.save_snapshot(self.config.stage2_daily_path(market_date), payload)
        StorageService.save_snapshot(self.config.stage2_latest_path, payload)

    def health_payload(self) -> Tuple[bool, Dict[str, Any]]:
        now = self.market_time.now()
        session = self.market_calendar.session_status()
        age = max(0.0, (now - self.last_global_packet_at).total_seconds()) if self.last_global_packet_at else None
        if not session.is_trading_day:
            healthy, reason = True, session.reason or "non_trading_day"
        elif self.connection_state == "WAITING_FOR_START" and session.is_before_open:
            healthy, reason = True, "waiting_for_configured_start"
        elif not self.universe_version:
            healthy, reason = False, "universe_unavailable"
        elif session.is_before_open:
            healthy, reason = self.connection_state in {"CONNECTED", "WAITING_FOR_START"}, "preopen"
        elif session.is_after_close:
            healthy, reason = True, "session_ended"
        elif self.connection_state != "CONNECTED":
            healthy, reason = False, "feed_disconnected"
        elif age is None or age > self.config.intra_finder_global_idle_seconds:
            healthy, reason = False, "global_packet_idle"
        else:
            healthy, reason = True, "live"
        return healthy, {
            "status": "healthy" if healthy else "unhealthy",
            "reason": reason,
            "market_date": self.market_time.market_date_str(),
            "universe_version": self.universe_version,
            "universe_source_date": self.universe_source_date,
            "connection_state": self.connection_state,
            "expected_instruments": len(self.stocks),
            "observed_instruments": len(self.received_keys),
            "hot_instruments": len(self.last_ranking.hot),
            "rank_duration_ms": round(self.last_rank_duration_ms, 3),
            "last_global_packet_at": self.last_global_packet_at.isoformat() if self.last_global_packet_at else None,
            "global_packet_age_seconds": round(age, 3) if age is not None else None,
            "reconnect_count": self.reconnect_count,
            "shadow_mode": self.shadow_mode,
            "detector_mode": self.detector_mode,
            "agent_dispatch_active": len(self.agent_threads),
        }

    def enforce_retention(self) -> None:
        root = self.config.stage2_results_dir.resolve()
        if root.name != "stage2" or self.config.results_dir.resolve() not in root.parents:
            raise RuntimeError("Refusing retention outside the configured Stage 2 directory.")
        if not root.exists():
            return
        today = self.market_time.now().date()
        for path in root.iterdir():
            if not path.is_dir():
                continue
            try:
                age = (today - date.fromisoformat(path.name)).days
            except ValueError:
                continue
            raw = path / "raw-depth"
            if age > self.config.intra_finder_raw_retention_days and raw.exists():
                shutil.rmtree(raw)
            one_second = path / "one-second"
            if age > self.config.intra_finder_derived_retention_days and one_second.exists():
                shutil.rmtree(one_second)

    def _universe_version_changed(self) -> bool:
        payload = StorageService.load_snapshot(self.config.stage1_latest_path) or {}
        version = str((payload.get("summary") or {}).get("universe_version") or "")
        return bool(version and self.universe_version and version != self.universe_version)

    def _get_feed_data(self, feed: Any) -> Any:
        timeout = (
            self.config.intra_finder_preopen_idle_seconds
            if self.session_state == "PREOPEN"
            else self.config.intra_finder_global_idle_seconds
        )
        try:
            return feed.loop.run_until_complete(
                asyncio.wait_for(feed.get_instrument_data(), timeout=max(10, timeout))
            )
        except asyncio.TimeoutError as exc:
            raise FeedIdleTimeout(f"no_market_packet_for_{timeout}_seconds") from exc

    @staticmethod
    def _close_feed(feed: Any) -> None:
        if feed is None:
            return
        for name in ("disconnect", "close_connection"):
            try:
                method = getattr(feed, name, None)
                if method is None:
                    continue
                result = method()
                if asyncio.iscoroutine(result):
                    feed.loop.run_until_complete(result)
                return
            except Exception:
                continue

    def _mark_session_ended(self, market_date: str) -> None:
        self.session_state = "SESSION_ENDED"
        self.connection_state = "SESSION_ENDED"
        for state in self.states.values():
            state.status = "SESSION_ENDED"
        self.flush(force_checkpoint=True, checkpoint_market_date=market_date)
        self._save_status_if_due(force=True)

    def _wait_for_pending_io(self) -> bool:
        for future in list(self.io_futures):
            try:
                future.result()
            except Exception as exc:
                self._log(f"Final persistence failed; retaining memory: {type(exc).__name__}: {exc}")
                return False
        self.io_futures.clear()
        return True

    def _release_session_memory(self, market_date: str) -> int:
        count = len(self.states)
        with self.state_lock:
            self.states.clear()
            getattr(self, "stocks", {}).clear()
            getattr(self, "security_index", {}).clear()
            getattr(self, "stocks_by_security_id", {}).clear()
            self.universe_payload = {}
            self.universe_version = ""
            self.universe_source_date = ""
            self.raw_buffer.clear()
            self.derived_buffer.clear()
            self.event_state = {}
        for name in (
            "received_keys", "full_packet_keys", "quote_verified_keys",
            "coverage_milestones_logged", "opening_recovery_requested",
            "gate_failure_counts", "received_security_ids", "full_packet_security_ids",
            "quote_verified_security_ids", "pending_indicator_deadlines",
        ):
            collection = getattr(self, name, None)
            if collection is not None:
                collection.clear()
        self.last_ranking = RankingResult([], [], 0)
        self.released_session_date = market_date
        release_unused_process_memory()
        return count

    def _finalize_and_release_session(self, market_date: str) -> None:
        if self.released_session_date == market_date:
            return
        self._mark_session_ended(market_date)
        if not self._wait_for_pending_io():
            return
        count = self._release_session_memory(market_date)
        self._log(f"Session memory released for {market_date}; states={count:,}.")

    def run_forever(self) -> None:
        while True:
            feed = None
            try:
                session = self.market_calendar.session_status()
                if not session.is_trading_day:
                    if self.states:
                        self._finalize_and_release_session(session.market_date)
                    self.session_state = "MARKET_CLOSED"
                    self.connection_state = "WAITING_FOR_TRADING_DAY"
                    time.sleep(300)
                    continue
                market_open = datetime.fromisoformat(session.open_at_ist)
                feed_start = market_open - timedelta(minutes=5)
                if self.market_time.now() < feed_start:
                    self.session_state = "PREOPEN"
                    self.connection_state = "WAITING_FOR_START"
                    time.sleep(30)
                    continue
                if session.is_after_close:
                    self._finalize_and_release_session(session.market_date)
                    time.sleep(300)
                    continue
                stocks = self.load_universe()
                instruments = self.build_instruments(stocks)
                self._log(
                    f"Starting Full Packet feed; instruments={len(instruments):,} "
                    f"universe_source={self.universe_source_date} detector={self.detector_mode} "
                    f"shadow={self.shadow_mode}."
                )
                feed = self.dhan.build_marketfeed(instruments)
                credential_version = self.dhan.credential_version
                feed.run_forever()
                self.dhan.configure_marketfeed_websocket(feed)
                self.current_feed = feed
                self.received_keys.clear()
                self.full_packet_keys.clear()
                self.quote_verified_keys.clear()
                self.coverage_milestones_logged.clear()
                self.connection_generation += 1
                self.last_global_packet_at = None
                self.connected_at = self.market_time.now()
                self.connection_state = "CONNECTED"
                self.session_state = "PREOPEN" if session.is_before_open else "LIVE"
                self.last_connection_error = None
                last_session_check = time.monotonic()
                while True:
                    if self.dhan.reload_credentials_if_changed() or self.dhan.credential_version != credential_version:
                        raise RuntimeError("credential_rotated")
                    if time.monotonic() - last_session_check >= 30:
                        current = self.market_calendar.session_status()
                        if current.is_after_close:
                            raise SessionEnded("market_session_ended")
                        if self._universe_version_changed():
                            raise RuntimeError("universe_rotated")
                        self.session_state = "PREOPEN" if current.is_before_open else "LIVE"
                        self._start_opening_range_recovery()
                        self._start_coverage_verification()
                        last_session_check = time.monotonic()
                    packet = self._get_feed_data(feed)
                    if isinstance(packet, dict):
                        self.process_packet(packet)
            except SessionEnded:
                self._close_feed(feed)
                self.current_feed = None
                self._finalize_and_release_session(self.market_calendar.session_status().market_date)
                time.sleep(300)
            except (FileNotFoundError, RuntimeError) as exc:
                if isinstance(exc, FileNotFoundError) or "Universe Scanner" in str(exc):
                    self.universe_wait_count += 1
                    self.connection_state = "WAITING_FOR_UNIVERSE"
                    self.last_connection_error = type(exc).__name__
                    time.sleep(5)
                    continue
                self._handle_reconnect(feed, exc)
            except Exception as exc:
                self._handle_reconnect(feed, exc)

    def _handle_reconnect(self, feed: Any, exc: Exception) -> None:
        self.reconnect_count += 1
        self.connection_state = "RECONNECTING"
        self.last_connection_error = type(exc).__name__
        self._log(f"Reconnecting after {type(exc).__name__}.")
        self.flush()
        self._save_status_if_due(force=True)
        self._close_feed(feed)
        self.current_feed = None
        time.sleep(5)

    def close(self) -> None:
        self._close_feed(self.current_feed)
        self.flush(force_checkpoint=True)
        self._save_status_if_due(force=True)
        self.recovery_executor.shutdown(wait=False, cancel_futures=True)
        self.io_executor.shutdown(wait=True, cancel_futures=False)


def _signal_priority(signal: SetupSignal) -> int:
    priorities = {
        "OPENING_DRIVE": 0,
        "GAP_REJECTION": 1,
        "OPENING_RANGE_ACCEPTANCE": 2,
        "VOLATILITY_IGNITION": 3,
        "VWAP_REVERSION": 4,
    }
    return priorities.get(signal.family, 99)


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
