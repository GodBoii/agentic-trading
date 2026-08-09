"""Stage 2: continuous Full Packet monitoring and event-driven setup detection."""

from __future__ import annotations

import asyncio
import heapq
import hashlib
import json
import os
import shutil
import time
import uuid
from collections import Counter, defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
from dhanhq import MarketFeed

from pipeline.config import PipelineConfig
from pipeline.models import SetupEvent
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.market_calendar_service import MarketCalendarService
from pipeline.services.storage_service import StorageService
from pipeline.stages.indicator_event_engine import IndicatorEventEngine


def subscription_batches(instruments: List[tuple], size: int = 100) -> List[List[tuple]]:
    if size <= 0:
        raise ValueError("subscription batch size must be positive")
    return [instruments[index : index + size] for index in range(0, len(instruments), size)]


class FeedIdleTimeout(RuntimeError):
    pass


class SessionEnded(RuntimeError):
    pass


class IntraFinder:
    EVENT_STATE_SCHEMA_VERSION = 5
    RUNTIME_STATE_SCHEMA_VERSION = 4

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config, prefer_gateway=False)
        self.historical_dhan = DhanService(self.config, prefer_gateway=True)
        self.market_time = MarketTimeService(self.config)
        self.market_calendar = MarketCalendarService(self.config)
        self.universe_payload: Dict[str, Any] = {}
        self.universe_version = ""
        self.stocks_by_security_id: Dict[int, Dict[str, Any]] = {}
        self.states: Dict[int, Dict[str, Any]] = {}
        self.raw_buffer: List[Dict[str, Any]] = []
        self.derived_buffer: List[Dict[str, Any]] = []
        self.last_flush = time.time()
        self.last_status_save = 0.0
        self.packet_count = 0
        self.reconnect_count = 0
        self.universe_wait_count = 0
        self.events_formed = 0
        self.events_triggered = 0
        self.events_suppressed = 0
        self.received_security_ids: set[int] = set()
        self.full_packet_security_ids: set[int] = set()
        self.quote_verified_security_ids: set[int] = set()
        self.connection_generation = 0
        self.coverage_verification_future: Optional[Future] = None
        self.last_global_packet_at: Optional[datetime] = None
        self.connected_at: Optional[datetime] = None
        self.connection_state = "STARTING"
        self.last_connection_error: Optional[str] = None
        self.session_state = "STARTING"
        self.state_lock = RLock()
        self.dispatch_lock = RLock()
        self.current_feed: Any = None
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, self.config.intra_finder_agent_concurrency)
        )
        self.io_executor = ThreadPoolExecutor(max_workers=1)
        self.io_futures: set[Future] = set()
        self.recovery_executor = ThreadPoolExecutor(max_workers=4)
        self.recovery_futures: set[Future] = set()
        self.opening_range_recovery_started = False
        self.opening_range_recovery_requested = 0
        self.opening_range_recovery_completed = 0
        self.opening_range_recovery_failed = 0
        self.agent_futures: set[Future] = set()
        self.pending_agent_events: List[Dict[str, Any]] = []
        self.agent_dispatch_successes = 0
        self.agent_dispatch_failures = 0
        self.agent_queue_expired = 0
        self.agent_queue_overflow_dropped = 0
        self.event_state: Dict[str, Any] = {}
        self.shadow_mode = os.getenv(
            "INTRA_FINDER_SHADOW_MODE",
            "1" if self.config.intra_finder_shadow_mode else "0",
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.candidates_seen = 0
        self.gate_failure_counts: Counter[str] = Counter()
        self.last_progress_log = 0.0
        self.progress_log_seconds = max(
            10, int(os.getenv("INTRA_FINDER_PROGRESS_LOG_SECONDS", "60"))
        )
        self.coverage_milestones_logged: set[int] = set()
        self.detector_mode = "indicator_events"
        self.indicator_aggregation_seconds = max(
            1,
            int(
                os.getenv(
                    "INTRA_FINDER_INDICATOR_AGGREGATION_SECONDS",
                    str(self.config.intra_finder_indicator_aggregation_seconds),
                )
            ),
        )
        self.stock_agent_cooldown_seconds = max(
            0,
            int(
                os.getenv(
                    "INTRA_FINDER_STOCK_AGENT_COOLDOWN_SECONDS",
                    str(self.config.intra_finder_stock_agent_cooldown_seconds),
                )
            ),
        )
        self.agent_queue_max = max(
            1,
            int(
                os.getenv(
                    "INTRA_FINDER_AGENT_QUEUE_MAX",
                    str(self.config.intra_finder_agent_queue_max),
                )
            ),
        )
        self.agent_queue_max_age_seconds = max(
            1,
            int(
                os.getenv(
                    "INTRA_FINDER_AGENT_QUEUE_MAX_AGE_SECONDS",
                    str(self.config.intra_finder_agent_queue_max_age_seconds),
                )
            ),
        )
        self.indicator_engine = IndicatorEventEngine(
            volume_surge_ratio=float(
                os.getenv(
                    "INTRA_FINDER_INDICATOR_VOLUME_SURGE_RATIO",
                    str(self.config.intra_finder_indicator_volume_surge_ratio),
                )
            ),
            event_cooldown_seconds=max(
                0,
                int(
                    os.getenv(
                        "INTRA_FINDER_INDICATOR_EVENT_COOLDOWN_SECONDS",
                        str(self.config.intra_finder_indicator_event_cooldown_seconds),
                    )
                ),
            ),
            max_event_lag_seconds=max(
                0,
                int(
                    os.getenv(
                        "INTRA_FINDER_INDICATOR_MAX_EVENT_LAG_SECONDS",
                        str(self.config.intra_finder_indicator_max_event_lag_seconds),
                    )
                ),
            ),
        )
        self.pending_indicator_deadlines: List[Tuple[float, int, int]] = []
        self.indicator_events_detected = 0
        self.indicator_aggregates_formed = 0

    def _log(self, message: str) -> None:
        print(
            f"[{self.market_time.now().strftime('%Y-%m-%d %H:%M:%S %Z')}] "
            f"[Intra-Finder] {message}",
            flush=True,
        )

    def _log_progress(self, summary: Dict[str, Any], *, force: bool = False) -> None:
        now = time.time()
        last_progress_log = float(getattr(self, "last_progress_log", 0.0))
        progress_log_seconds = int(getattr(self, "progress_log_seconds", 60))
        if not force and now - last_progress_log < progress_log_seconds:
            return
        state_counts = Counter(str(state.get("state") or "UNKNOWN") for state in self.states.values())
        most_common_states = ", ".join(
            f"{name}={count}" for name, count in state_counts.most_common(4)
        ) or "none"
        common_gates = ", ".join(
            f"{name}={count}"
            for name, count in getattr(self, "gate_failure_counts", Counter()).most_common(4)
        ) or "none"
        self._log(
            f"LIVE STATUS | connection={summary['connection_state']} session={summary['session_state']} "
            f"packets={summary['packet_count']:,} observed={summary['observed_instruments']:,}/"
            f"{summary['expected_instruments']:,} full={summary['full_packet_instruments']:,} "
            f"active={summary['active_instruments']:,} stale={summary['stale_instruments']:,} "
            f"OR_ready={summary['opening_range_complete']:,} RVOL_ready={summary['rvol_available']:,} "
            f"indicator_events={summary['indicator_events_detected']:,} "
            f"aggregates={summary['indicator_aggregates_formed']:,} "
            f"pending={summary['pending_indicator_stocks']:,} events={summary['events_formed']:,} "
            f"agent_active={summary['agent_dispatch_active']:,} agent_queue={summary['agent_dispatch_queued']:,} "
            f"queue_expired={summary['agent_queue_expired']:,} queue_dropped={summary['agent_queue_overflow_dropped']:,} "
            f"suppressed={summary['events_suppressed']:,} reconnects={summary['reconnect_count']:,} "
            f"shadow={summary['shadow_mode']} | states: {most_common_states} | gates: {common_gates}"
        )
        self.last_progress_log = now

    def load_universe(self) -> List[Dict[str, Any]]:
        payload = StorageService.load_snapshot(self.config.stage1_latest_path)
        if not payload or payload.get("stage") != "universe_scanner":
            raise FileNotFoundError("A successful Universe Scanner snapshot is not available.")
        summary = payload.get("summary") or {}
        market_date = self.market_time.market_date_str()
        if summary.get("status") != "completed" or summary.get("market_date") != market_date:
            raise RuntimeError("Universe Scanner output is stale or degraded.")
        stocks = payload.get("stocks") or []
        if not stocks:
            raise RuntimeError("Universe Scanner returned no stocks.")
        old_version = self.universe_version
        old_market_date = str(
            (self.universe_payload.get("summary") or {}).get("market_date") or ""
        )
        new_version = str(summary.get("universe_version") or "")
        security_ids = [int(stock["security_id"]) for stock in stocks]
        if len(set(security_ids)) != len(security_ids):
            raise RuntimeError(
                "Universe Scanner produced exchange-colliding security IDs; "
                "Stage 2 refuses to silently overwrite venue identity."
            )
        new_stocks = {int(stock["security_id"]): stock for stock in stocks}
        identity_compatible = (
            old_market_date == market_date
            and set(self.stocks_by_security_id) == set(new_stocks)
        )
        same_universe = (
            bool(self.universe_version)
            and self.universe_version == new_version
            and set(self.stocks_by_security_id) == set(new_stocks)
        )
        self.universe_payload = payload
        self.universe_version = new_version
        self.stocks_by_security_id = new_stocks
        if not same_universe:
            if old_version and old_market_date != market_date:
                self.received_security_ids.clear()
                self.full_packet_security_ids.clear()
                self.packet_count = 0
                self.events_formed = 0
                self.events_triggered = 0
                self.events_suppressed = 0
                self.last_global_packet_at = None
                self.opening_range_recovery_started = False
                self.opening_range_recovery_requested = 0
                self.opening_range_recovery_completed = 0
                self.opening_range_recovery_failed = 0
                self.indicator_events_detected = 0
                self.indicator_aggregates_formed = 0
                self.pending_indicator_deadlines.clear()
            existing_states = self.states if identity_compatible else {}
            self.states = {
                security_id: existing_states.get(security_id) or self._new_state(stock)
                for security_id, stock in self.stocks_by_security_id.items()
            }
            self._restore_runtime_state(market_date)
            self._rebuild_indicator_deadlines()
            loaded_event_state = StorageService.load_snapshot(
                self.config.stage2_event_state_path(market_date)
            ) or {}
            if (
                int(loaded_event_state.get("schema_version") or 0)
                != self.EVENT_STATE_SCHEMA_VERSION
                or loaded_event_state.get("universe_version") != self.universe_version
            ):
                self.event_state = {
                    "schema_version": self.EVENT_STATE_SCHEMA_VERSION,
                    "universe_version": self.universe_version,
                    "events": {},
                    "active_setups": {},
                    "last_stock_event_at": {},
                    "superseded_event_count": len(loaded_event_state.get("events") or {}),
                }
                StorageService.save_snapshot(
                    self.config.stage2_event_state_path(market_date),
                    self.event_state,
                )
            else:
                self.event_state = loaded_event_state
        return stocks

    def _new_state(self, stock: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "security_id": int(stock["security_id"]),
            "state": "WARMING_UP",
            "last_packet_at": None,
            "last_any_packet_at": None,
            "first_packet_at": None,
            "last_price": None,
            "previous_volume": None,
            "day_volume": 0.0,
            "volume_deltas": deque(maxlen=420),
            "volume_started_at": None,
            "current_volume_second": None,
            "opening_range_high": None,
            "opening_range_low": None,
            "opening_range_complete": False,
            "opening_range_source": None,
            "orb_break": {
                "LONG": {"phase": "SEEK_BREAK", "crossed_at": None},
                "SHORT": {"phase": "SEEK_BREAK", "crossed_at": None},
            },
            "vwap": None,
            "was_below_vwap": False,
            "was_above_vwap": False,
            "vwap_reclaim": {
                "LONG": {
                    "phase": "SEEK_RECLAIM",
                    "reclaimed_at": None,
                    "extreme": None,
                    "pullback": None,
                    "pullback_at": None,
                },
                "SHORT": {
                    "phase": "SEEK_RECLAIM",
                    "reclaimed_at": None,
                    "extreme": None,
                    "pullback": None,
                    "pullback_at": None,
                },
            },
            "confirmations": {},
            "last_second": None,
            "last_suppressed_key": None,
            "latest_features": {},
            **IndicatorEventEngine.state_fields(),
        }

    @staticmethod
    def _state_checkpoint_fields() -> Tuple[str, ...]:
        return (
            "state",
            "last_packet_at",
            "last_any_packet_at",
            "first_packet_at",
            "last_price",
            "previous_volume",
            "day_volume",
            "volume_deltas",
            "volume_started_at",
            "current_volume_second",
            "opening_range_high",
            "opening_range_low",
            "opening_range_complete",
            "opening_range_source",
            "orb_break",
            "vwap",
            "was_below_vwap",
            "was_above_vwap",
            "vwap_reclaim",
            "confirmations",
            "last_second",
            "last_suppressed_key",
            "latest_features",
            "minute_builder",
            "minute_bars",
            "last_closed_cumulative_volume",
            "indicator_snapshot",
            "indicator_event_last_at",
            "pending_indicator_events",
            "pending_indicator_deadline",
            "pending_indicator_generation",
        )

    def _runtime_state_payload(self) -> Dict[str, Any]:
        states: Dict[str, Any] = {}
        with self.state_lock:
            for security_id, state in self.states.items():
                item: Dict[str, Any] = {}
                for key in self._state_checkpoint_fields():
                    value = state.get(key)
                    if isinstance(value, deque):
                        value = list(value)
                    if key == "latest_features" and isinstance(value, dict):
                        value = {name: detail for name, detail in value.items() if name != "depth"}
                    item[key] = value
                states[str(security_id)] = item
        return {
            "schema_version": self.RUNTIME_STATE_SCHEMA_VERSION,
            "market_date": self.market_time.market_date_str(),
            "universe_version": self.universe_version,
            "saved_at": self.market_time.now().isoformat(),
            "states": states,
        }

    def _restore_runtime_state(self, market_date: str) -> None:
        payload = StorageService.load_snapshot(self.config.stage2_runtime_state_path(market_date))
        if not payload or payload.get("market_date") != market_date or payload.get(
            "universe_version"
        ) != self.universe_version:
            return
        detector_compatible = (
            int(payload.get("schema_version") or 0) == self.RUNTIME_STATE_SCHEMA_VERSION
        )
        detector_fields = {
            "orb_break",
            "vwap_reclaim",
            "confirmations",
            "last_suppressed_key",
            "minute_builder",
            "minute_bars",
            "last_closed_cumulative_volume",
            "indicator_snapshot",
            "indicator_event_last_at",
            "pending_indicator_events",
            "pending_indicator_deadline",
            "pending_indicator_generation",
        }
        restored = 0
        for raw_security_id, saved in (payload.get("states") or {}).items():
            try:
                security_id = int(raw_security_id)
            except (TypeError, ValueError):
                continue
            state = self.states.get(security_id)
            if state is None or not isinstance(saved, dict):
                continue
            for key in self._state_checkpoint_fields():
                if key not in saved:
                    continue
                if not detector_compatible and key in detector_fields:
                    continue
                value = saved[key]
                if key == "volume_deltas":
                    value = deque(
                        (
                            (float(item[0]), float(item[1]))
                            for item in (value or [])
                            if isinstance(item, (list, tuple)) and len(item) == 2
                        ),
                        maxlen=420,
                    )
                if key == "minute_bars":
                    value = deque(
                        (item for item in (value or []) if isinstance(item, dict)),
                        maxlen=IndicatorEventEngine.BAR_LIMIT,
                    )
                state[key] = value
            restored += 1
        if restored:
            mode = "full" if detector_compatible else "market-data-only"
            print(f"Intra-Finder restored {mode} state for {restored} stocks.")

    def _rebuild_indicator_deadlines(self) -> None:
        self.pending_indicator_deadlines.clear()
        for security_id, state in self.states.items():
            if not state.get("pending_indicator_events"):
                continue
            deadline = state.get("pending_indicator_deadline")
            try:
                deadline_timestamp = datetime.fromisoformat(str(deadline)).timestamp()
            except (TypeError, ValueError):
                continue
            heapq.heappush(
                self.pending_indicator_deadlines,
                (
                    deadline_timestamp,
                    security_id,
                    int(state.get("pending_indicator_generation") or 0),
                ),
            )

    @staticmethod
    def _feed_exchange(stock: Dict[str, Any]) -> Any:
        segment = str(stock.get("exchange_segment") or "").upper()
        if segment == "NSE_EQ":
            return MarketFeed.NSE
        if segment == "BSE_EQ":
            return MarketFeed.BSE
        raise ValueError(f"Unsupported Intra-Finder exchange segment: {segment}")

    def build_instruments(self, stocks: Iterable[Dict[str, Any]]) -> List[tuple]:
        instruments = [
            (self._feed_exchange(stock), str(stock["security_id"]), MarketFeed.Full)
            for stock in stocks
        ]
        if len(instruments) > 5_000:
            raise RuntimeError(
                f"Intra-Finder universe has {len(instruments)} instruments; one Dhan connection supports 5000."
            )
        return instruments

    def _universe_version_changed(self) -> bool:
        payload = StorageService.load_snapshot(self.config.stage1_latest_path) or {}
        version = str((payload.get("summary") or {}).get("universe_version") or "")
        return bool(version and self.universe_version and version != self.universe_version)

    @staticmethod
    def _number(payload: Dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            try:
                if payload.get(key) not in (None, ""):
                    return float(payload[key])
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _depth(packet: Dict[str, Any]) -> List[Dict[str, float]]:
        rows: List[Dict[str, float]] = []
        for item in packet.get("depth") or []:
            if not isinstance(item, dict):
                continue
            parsed: Dict[str, float] = {}
            for key in ("bid_price", "ask_price", "bid_quantity", "ask_quantity", "bid_orders", "ask_orders"):
                try:
                    parsed[key] = float(item.get(key) or 0)
                except (TypeError, ValueError):
                    parsed[key] = 0.0
            rows.append(parsed)
        return rows[:5]

    @staticmethod
    def _rounded_five_minute(now: datetime) -> str:
        minute = (now.minute // 5) * 5
        return f"{now.hour:02d}:{minute:02d}"

    def _relative_volume(self, stock: Dict[str, Any], volume: float, now: datetime) -> Optional[float]:
        baselines = stock.get("intraday_baselines") or {}
        if baselines.get("status") != "ready" or int(baselines.get("schema_version") or 0) < 2:
            return None
        if str(baselines.get("timezone") or "") not in {"Asia/Kolkata", "Asia/Calcutta"}:
            return None
        baseline = baselines.get("median_cumulative_volume") or {}
        expected = baseline.get(self._rounded_five_minute(now))
        try:
            expected_value = float(expected)
            return volume / expected_value if expected_value > 0 else None
        except (TypeError, ValueError):
            return None

    def _volume_acceleration(
        self,
        deltas: Deque[Tuple[float, float]],
        now_ts: float,
        started_at: Optional[float],
    ) -> Optional[float]:
        if started_at is None or now_ts - float(started_at) < self.config.intra_finder_volume_warmup_seconds:
            return None
        recent = sum(value for ts, value in deltas if ts >= now_ts - 60)
        prior = sum(value for ts, value in deltas if now_ts - 360 <= ts < now_ts - 60)
        if prior <= 0:
            return None
        ratio = recent / (prior / 5.0)
        return min(float(self.config.intra_finder_volume_acceleration_cap), max(0.0, ratio))

    def _record_volume(
        self,
        state: Dict[str, Any],
        *,
        volume: float,
        now_ts: float,
    ) -> None:
        previous_volume = state.get("previous_volume")
        second = int(now_ts)
        if state.get("volume_started_at") is None:
            state["volume_started_at"] = now_ts
        if previous_volume is not None and volume < float(previous_volume):
            state["volume_deltas"].clear()
            state["volume_started_at"] = now_ts
            state["current_volume_second"] = None
        elif previous_volume is not None:
            delta = max(0.0, volume - float(previous_volume))
            if state.get("current_volume_second") == second and state["volume_deltas"]:
                prior_second, prior_delta = state["volume_deltas"].pop()
                state["volume_deltas"].append((prior_second, prior_delta + delta))
            else:
                state["volume_deltas"].append((float(second), delta))
                state["current_volume_second"] = second
        state["previous_volume"] = volume
        state["day_volume"] = volume

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
        quantity_needed = trade_amount / reference_price
        side_price = "ask_price" if direction == "LONG" else "bid_price"
        side_quantity = "ask_quantity" if direction == "LONG" else "bid_quantity"
        remaining = quantity_needed
        total_cost = 0.0
        filled = 0.0
        for level in depth:
            available = max(0.0, level.get(side_quantity, 0.0))
            price = max(0.0, level.get(side_price, 0.0))
            take = min(remaining, available)
            if take > 0 and price > 0:
                total_cost += take * price
                filled += take
                remaining -= take
            if remaining <= 0:
                break
        if filled < quantity_needed * 0.95 or filled <= 0:
            return None
        average_price = total_cost / filled
        return abs(average_price - reference_price) / reference_price * 100

    def _update_opening_range(self, state: Dict[str, Any], price: float, now: datetime) -> None:
        current = now.time()
        start = dt_time(9, 15)
        end = dt_time(9, 30)
        if start <= current < end:
            high = state["opening_range_high"]
            low = state["opening_range_low"]
            state["opening_range_high"] = price if high is None else max(float(high), price)
            state["opening_range_low"] = price if low is None else min(float(low), price)
            state["opening_range_source"] = "live_feed"
            state["state"] = "WARMING_UP"
        elif current >= end and state["opening_range_high"] is not None:
            state["opening_range_complete"] = True
            if state["state"] == "WARMING_UP":
                state["state"] = "WATCHING"

    def _fetch_opening_range(
        self,
        stock: Dict[str, Any],
    ) -> Tuple[int, Optional[float], Optional[float], Optional[str]]:
        security_id = int(stock["security_id"])
        try:
            response = self.historical_dhan.fetch_intraday_history(
                security_id,
                days=1,
                interval=1,
                retries=2,
                exchange_segment=str(stock["exchange_segment"]),
                instrument_candidates=["EQUITY"],
            )
            if not response or str(response.get("status") or "").lower() != "success":
                return security_id, None, None, "historical_request_failed"
            frame = self.historical_dhan.intraday_response_to_df(response)
            if frame.empty:
                return security_id, None, None, "historical_response_empty"
            timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
            frame["timestamp"] = timestamps.dt.tz_convert(self.market_time.tz)
            frame = frame.dropna(subset=["timestamp"])
            today = self.market_time.now().date()
            opening = frame[
                (frame["timestamp"].dt.date == today)
                & (frame["timestamp"].dt.time >= dt_time(9, 15))
                & (frame["timestamp"].dt.time < dt_time(9, 30))
            ].copy()
            opening["high"] = pd.to_numeric(opening["high"], errors="coerce")
            opening["low"] = pd.to_numeric(opening["low"], errors="coerce")
            opening = opening.dropna(subset=["high", "low"])
            if opening["timestamp"].dt.floor("min").nunique() < 12:
                return security_id, None, None, "opening_range_incomplete"
            return (
                security_id,
                float(opening["high"].max()),
                float(opening["low"].min()),
                None,
            )
        except Exception as exc:
            return security_id, None, None, f"{type(exc).__name__}"

    def _apply_opening_range_recovery(self, future: Future) -> None:
        try:
            security_id, high, low, error = future.result()
        except Exception:
            self.opening_range_recovery_failed += 1
            return
        state = self.states.get(int(security_id))
        if state is None:
            return
        if error or high is None or low is None:
            self.opening_range_recovery_failed += 1
            return
        with self.state_lock:
            if not state.get("opening_range_complete"):
                state["opening_range_high"] = high
                state["opening_range_low"] = low
                state["opening_range_complete"] = True
                state["opening_range_source"] = "historical_recovery"
                if state.get("state") == "WARMING_UP":
                    state["state"] = "WATCHING"
        self.opening_range_recovery_completed += 1

    def _start_opening_range_recovery(self) -> None:
        if self.opening_range_recovery_started or self.market_time.now().time() < dt_time(9, 30):
            return
        missing = [
            stock
            for security_id, stock in self.stocks_by_security_id.items()
            if not self.states[security_id].get("opening_range_complete")
        ]
        if not missing:
            self.opening_range_recovery_started = True
            return
        self.opening_range_recovery_started = True
        self.opening_range_recovery_requested = len(missing)
        print(
            f"Intra-Finder recovering missed opening ranges for {len(missing)} stocks "
            "through the shared historical-data gateway."
        )
        for stock in missing:
            future = self.recovery_executor.submit(self._fetch_opening_range, stock)
            self.recovery_futures.add(future)
            future.add_done_callback(self._apply_opening_range_recovery)

    def _verify_unobserved_instruments(
        self,
        generation: int,
        missing: List[Dict[str, Any]],
    ) -> Tuple[int, set[int]]:
        verified: set[int] = set()
        by_segment: Dict[str, List[int]] = defaultdict(list)
        for stock in missing:
            by_segment[str(stock["exchange_segment"])].append(int(stock["security_id"]))
        for segment, security_ids in by_segment.items():
            try:
                quotes = self.historical_dhan.fetch_quote_batch(
                    security_ids,
                    exchange_segment=segment,
                )
                verified.update(
                    int(security_id)
                    for security_id, quote in (quotes or {}).items()
                    if isinstance(quote, dict) and quote
                )
            except Exception:
                continue
        return generation, verified

    def _apply_coverage_verification(self, future: Future) -> None:
        try:
            generation, verified = future.result()
        except Exception:
            return
        if generation == self.connection_generation:
            self.quote_verified_security_ids.update(verified)

    def _start_coverage_verification(self) -> None:
        if not self.connected_at:
            return
        if (
            self.market_time.now() - self.connected_at
        ).total_seconds() < self.config.intra_finder_subscription_verify_seconds:
            return
        if self.coverage_verification_future and not self.coverage_verification_future.done():
            return
        missing = [
            stock
            for security_id, stock in self.stocks_by_security_id.items()
            if security_id not in self.received_security_ids
            and security_id not in self.quote_verified_security_ids
        ]
        if not missing:
            return
        future = self.recovery_executor.submit(
            self._verify_unobserved_instruments,
            self.connection_generation,
            missing,
        )
        self.coverage_verification_future = future
        future.add_done_callback(self._apply_coverage_verification)

    def _depth_features(self, depth: List[Dict[str, float]], price: float) -> Dict[str, Any]:
        bids = sum(level["bid_quantity"] for level in depth)
        asks = sum(level["ask_quantity"] for level in depth)
        bid_orders = sum(level["bid_orders"] for level in depth)
        ask_orders = sum(level["ask_orders"] for level in depth)
        best_bid = max((level["bid_price"] for level in depth if level["bid_price"] > 0), default=0.0)
        best_ask = min((level["ask_price"] for level in depth if level["ask_price"] > 0), default=0.0)
        spread = ((best_ask - best_bid) / price * 100) if price > 0 and best_ask >= best_bid > 0 else None
        return {
            "best_bid": best_bid or None,
            "best_ask": best_ask or None,
            "spread_percent": round(spread, 5) if spread is not None else None,
            "bid_quantity_5": bids,
            "ask_quantity_5": asks,
            "depth_imbalance": ((bids - asks) / (bids + asks)) if bids + asks > 0 else 0.0,
            "order_count_imbalance": (
                (bid_orders - ask_orders) / (bid_orders + ask_orders)
                if bid_orders + ask_orders > 0
                else 0.0
            ),
        }

    def _setup_candidate(
        self,
        state: Dict[str, Any],
        features: Dict[str, Any],
        now: datetime,
    ) -> Optional[Tuple[str, str]]:
        price = float(features["last_price"])
        vwap = float(features.get("vwap") or 0)
        previous_price = float(features.get("previous_price") or price)
        if vwap > 0:
            if price < vwap:
                state["was_below_vwap"] = True
            if price > vwap:
                state["was_above_vwap"] = True

        candidates: List[Tuple[str, str]] = []
        if state["opening_range_complete"]:
            high = float(state["opening_range_high"])
            low = float(state["opening_range_low"])
            buffer_fraction = self.config.intra_finder_orb_break_buffer_percent / 100.0
            long_threshold = high * (1 + buffer_fraction)
            short_threshold = low * (1 - buffer_fraction)
            long_break = state["orb_break"]["LONG"]
            short_break = state["orb_break"]["SHORT"]

            if price <= high:
                long_break.update({"phase": "SEEK_BREAK", "crossed_at": None})
                state["confirmations"].pop("ORB:LONG", None)
            elif (
                long_break["phase"] == "SEEK_BREAK"
                and previous_price <= long_threshold <= price
            ):
                long_break.update({"phase": "BROKEN", "crossed_at": now.timestamp()})
            if price >= low:
                short_break.update({"phase": "SEEK_BREAK", "crossed_at": None})
                state["confirmations"].pop("ORB:SHORT", None)
            elif (
                short_break["phase"] == "SEEK_BREAK"
                and previous_price >= short_threshold >= price
            ):
                short_break.update({"phase": "BROKEN", "crossed_at": now.timestamp()})

            if long_break["phase"] == "BROKEN" and price >= long_threshold:
                candidates.append(("ORB", "LONG"))
            elif short_break["phase"] == "BROKEN" and price <= short_threshold:
                candidates.append(("ORB", "SHORT"))

        if vwap > 0:
            extension = self.config.intra_finder_vwap_extension_percent / 100.0
            tolerance = self.config.intra_finder_vwap_pullback_tolerance_percent / 100.0
            continuation = self.config.intra_finder_vwap_continuation_percent / 100.0

            long_flow = state["vwap_reclaim"]["LONG"]
            if (
                long_flow.get("reclaimed_at")
                and now.timestamp() - float(long_flow["reclaimed_at"])
                > self.config.intra_finder_vwap_max_sequence_seconds
            ):
                long_flow.update(
                    {
                        "phase": "SEEK_RECLAIM",
                        "reclaimed_at": None,
                        "extreme": None,
                        "pullback": None,
                        "pullback_at": None,
                    }
                )
            if price < vwap:
                state["confirmations"].pop("VWAP_RECLAIM_PULLBACK:LONG", None)
                long_flow.update(
                    {
                        "phase": "SEEK_RECLAIM",
                        "reclaimed_at": None,
                        "extreme": None,
                        "pullback": None,
                        "pullback_at": None,
                    }
                )
            elif (
                long_flow["phase"] == "SEEK_RECLAIM"
                and state["was_below_vwap"]
                and previous_price <= vwap < price
            ):
                long_flow.update(
                    {
                        "phase": "RECLAIMED",
                        "reclaimed_at": now.timestamp(),
                        "extreme": price,
                        "pullback": None,
                        "pullback_at": None,
                    }
                )
            elif long_flow["phase"] in {"RECLAIMED", "EXTENDED"}:
                long_flow["extreme"] = max(float(long_flow.get("extreme") or price), price)
                if float(long_flow["extreme"]) >= vwap * (1 + extension):
                    long_flow["phase"] = "EXTENDED"
                if (
                    long_flow["phase"] == "EXTENDED"
                    and price <= vwap * (1 + tolerance)
                    and now.timestamp() - float(long_flow.get("reclaimed_at") or now.timestamp()) >= 3
                ):
                    long_flow.update(
                        {"phase": "PULLBACK", "pullback": price, "pullback_at": now.timestamp()}
                    )
            elif long_flow["phase"] in {"PULLBACK", "CONTINUING"}:
                pullback = float(long_flow.get("pullback") or vwap)
                if (
                    price >= pullback * (1 + continuation)
                    and now.timestamp() - float(long_flow.get("pullback_at") or now.timestamp())
                    >= self.config.intra_finder_vwap_pullback_hold_seconds
                ):
                    long_flow["phase"] = "CONTINUING"
                    candidates.append(("VWAP_RECLAIM_PULLBACK", "LONG"))

            short_flow = state["vwap_reclaim"]["SHORT"]
            if (
                short_flow.get("reclaimed_at")
                and now.timestamp() - float(short_flow["reclaimed_at"])
                > self.config.intra_finder_vwap_max_sequence_seconds
            ):
                short_flow.update(
                    {
                        "phase": "SEEK_RECLAIM",
                        "reclaimed_at": None,
                        "extreme": None,
                        "pullback": None,
                        "pullback_at": None,
                    }
                )
            if price > vwap:
                state["confirmations"].pop("VWAP_RECLAIM_PULLBACK:SHORT", None)
                short_flow.update(
                    {
                        "phase": "SEEK_RECLAIM",
                        "reclaimed_at": None,
                        "extreme": None,
                        "pullback": None,
                        "pullback_at": None,
                    }
                )
            elif (
                short_flow["phase"] == "SEEK_RECLAIM"
                and state["was_above_vwap"]
                and previous_price >= vwap > price
            ):
                short_flow.update(
                    {
                        "phase": "RECLAIMED",
                        "reclaimed_at": now.timestamp(),
                        "extreme": price,
                        "pullback": None,
                        "pullback_at": None,
                    }
                )
            elif short_flow["phase"] in {"RECLAIMED", "EXTENDED"}:
                short_flow["extreme"] = min(float(short_flow.get("extreme") or price), price)
                if float(short_flow["extreme"]) <= vwap * (1 - extension):
                    short_flow["phase"] = "EXTENDED"
                if (
                    short_flow["phase"] == "EXTENDED"
                    and price >= vwap * (1 - tolerance)
                    and now.timestamp() - float(short_flow.get("reclaimed_at") or now.timestamp()) >= 3
                ):
                    short_flow.update(
                        {"phase": "PULLBACK", "pullback": price, "pullback_at": now.timestamp()}
                    )
            elif short_flow["phase"] in {"PULLBACK", "CONTINUING"}:
                pullback = float(short_flow.get("pullback") or vwap)
                if (
                    price <= pullback * (1 - continuation)
                    and now.timestamp() - float(short_flow.get("pullback_at") or now.timestamp())
                    >= self.config.intra_finder_vwap_pullback_hold_seconds
                ):
                    short_flow["phase"] = "CONTINUING"
                    candidates.append(("VWAP_RECLAIM_PULLBACK", "SHORT"))

        if not candidates:
            state["state"] = "WATCHING" if state["opening_range_complete"] else "WARMING_UP"
            return None
        setup, direction = candidates[0]
        key = f"{setup}:{direction}"
        bucket_seconds = max(1, self.config.intra_finder_confirmation_bucket_seconds)
        bucket = int(now.timestamp()) // bucket_seconds
        tracker = state["confirmations"].setdefault(
            key,
            {
                "count": 0,
                "first_seen_at": now.timestamp(),
                "last_seen_at": now.timestamp(),
                "last_bucket": None,
            },
        )
        last_bucket = tracker.get("last_bucket")
        if last_bucket is not None and bucket - int(last_bucket) > 1:
            tracker.update(
                {
                    "count": 0,
                    "first_seen_at": now.timestamp(),
                    "last_seen_at": now.timestamp(),
                    "last_bucket": None,
                }
            )
        if tracker.get("last_bucket") != bucket:
            tracker["count"] = int(tracker.get("count") or 0) + 1
            tracker["last_bucket"] = bucket
        tracker["last_seen_at"] = now.timestamp()
        elapsed = now.timestamp() - float(tracker.get("first_seen_at") or now.timestamp())
        armed = (
            int(tracker["count"]) >= self.config.intra_finder_confirmation_buckets
            and elapsed >= self.config.intra_finder_min_confirmation_seconds
        )
        state["state"] = "ARMED" if armed else "FORMING"
        return setup, direction

    def _score(
        self,
        setup: str,
        direction: str,
        state: Dict[str, Any],
        features: Dict[str, Any],
    ) -> Tuple[float, Dict[str, float]]:
        confirmation_key = f"{setup}:{direction}"
        confirmation = state["confirmations"].get(confirmation_key) or {}
        structure = 35.0 if state["state"] == "ARMED" else 20.0
        rvol = features.get("relative_volume")
        acceleration = features.get("volume_acceleration")
        volume_score = 0.0
        if rvol is not None:
            volume_score += min(14.0, max(0.0, (float(rvol) - 0.8) * 20))
        if acceleration is not None:
            volume_score += min(6.0, max(0.0, (float(acceleration) - 0.8) * 10))
        imbalance = float(features.get("depth_imbalance") or 0.0)
        directional_imbalance = imbalance if direction == "LONG" else -imbalance
        depth_score = min(20.0, max(0.0, 10.0 + directional_imbalance * 25.0))
        spread = features.get("spread_percent")
        slippage = features.get("estimated_slippage_percent")
        liquidity_score = 0.0
        if spread is not None:
            liquidity_score += max(
                0.0,
                10.0 * (1 - float(spread) / self.config.intra_finder_max_spread_percent),
            )
        if slippage is not None:
            liquidity_score += max(0.0, 5.0 * (1 - float(slippage) / 0.20))
        quality_score = 10.0 if features.get("data_fresh") and len(features.get("depth") or []) >= 5 else 5.0
        components = {
            "structure": round(structure, 2),
            "volume": round(min(20.0, volume_score), 2),
            "depth": round(depth_score, 2),
            "liquidity": round(min(15.0, liquidity_score), 2),
            "data_quality": round(quality_score, 2),
        }
        return round(sum(components.values()), 2), components

    def _hard_gates(self, features: Dict[str, Any], direction: str) -> List[str]:
        failures: List[str] = []
        if not features.get("data_fresh"):
            failures.append("DATA_STALE")
        if len(features.get("depth") or []) < 5:
            failures.append("DEPTH_INCOMPLETE")
        spread = features.get("spread_percent")
        if spread is None or float(spread) > self.config.intra_finder_max_spread_percent:
            failures.append("SPREAD_TOO_WIDE")
        slippage = features.get("estimated_slippage_percent")
        if slippage is None or float(slippage) > 0.20:
            failures.append("INSUFFICIENT_DEPTH_CAPACITY")
        rvol = features.get("relative_volume")
        acceleration = features.get("volume_acceleration")
        if rvol is None:
            failures.append("RVOL_BASELINE_UNAVAILABLE")
        elif float(rvol) < self.config.intra_finder_min_rvol_floor:
            failures.append("RVOL_BELOW_FLOOR")
        elif not (
            float(rvol) >= self.config.intra_finder_min_rvol
            or (
                acceleration is not None
                and float(acceleration) >= self.config.intra_finder_min_volume_acceleration
            )
        ):
            failures.append("VOLUME_NOT_CONFIRMED")
        if not features.get("connection_warm"):
            failures.append("CONNECTION_WARMING_UP")
        imbalance = float(features.get("depth_imbalance") or 0)
        if direction == "LONG" and imbalance < -0.35:
            failures.append("DEPTH_OPPOSES_DIRECTION")
        if direction == "SHORT" and imbalance > 0.35:
            failures.append("DEPTH_OPPOSES_DIRECTION")
        price = float(features.get("last_price") or 0)
        try:
            upper = float(features.get("upper_circuit") or 0)
            if direction == "LONG" and upper > 0 and price >= upper * 0.998:
                failures.append("UPPER_CIRCUIT_PROXIMITY")
        except (TypeError, ValueError):
            pass
        try:
            lower = float(features.get("lower_circuit") or 0)
            if direction == "SHORT" and lower > 0 and price <= lower * 1.002:
                failures.append("LOWER_CIRCUIT_PROXIMITY")
        except (TypeError, ValueError):
            pass
        try:
            now = datetime.fromisoformat(str(features.get("received_at"))).time()
        except (TypeError, ValueError):
            now = self.market_time.now().time()
        if now >= dt_time(15, 0):
            failures.append("ENTRY_CUTOFF")
        return failures

    @staticmethod
    def _indicator_direction(events: List[Dict[str, Any]]) -> str:
        directions = {
            str(event.get("direction") or "NEUTRAL")
            for event in events
            if str(event.get("direction") or "NEUTRAL") in {"LONG", "SHORT"}
        }
        if directions == {"LONG"}:
            return "LONG"
        if directions == {"SHORT"}:
            return "SHORT"
        if directions == {"LONG", "SHORT"}:
            return "MIXED"
        return "NEUTRAL"

    @staticmethod
    def _indicator_attention_score(events: List[Dict[str, Any]]) -> float:
        weights = {
            "DOJI": 1,
            "HAMMER": 2,
            "SHOOTING_STAR": 2,
            "BULLISH_ENGULFING": 3,
            "BEARISH_ENGULFING": 3,
            "EMA_BULLISH_CROSS": 3,
            "EMA_BEARISH_CROSS": 3,
            "RSI_ENTERED_OVERSOLD": 2,
            "RSI_ENTERED_OVERBOUGHT": 2,
            "RSI_EXITED_OVERSOLD": 3,
            "RSI_EXITED_OVERBOUGHT": 3,
            "VWAP_BULLISH_CROSS": 2,
            "VWAP_BEARISH_CROSS": 2,
            "ORB_BULLISH_CLOSE_BREAK": 3,
            "ORB_BEARISH_CLOSE_BREAK": 3,
            "VOLUME_SURGE": 2,
        }
        evidence_weight = sum(
            weights.get(str(event.get("event_type") or ""), 1) for event in events
        )
        # This is queue priority, not a probability of profit or a trade score.
        return float(min(100, 40 + evidence_weight * 8))

    def _queue_indicator_evidence(
        self,
        security_id: int,
        state: Dict[str, Any],
        events: List[Dict[str, Any]],
        detected_at: datetime,
    ) -> None:
        if not events:
            return
        pending = state.setdefault("pending_indicator_events", [])
        existing = {
            (str(item.get("event_type")), str(item.get("bar_start"))) for item in pending
        }
        evidence_limit = max(1, int(self.config.intra_finder_indicator_max_evidence))
        for event in events:
            key = (str(event.get("event_type")), str(event.get("bar_start")))
            if key not in existing and len(pending) < evidence_limit:
                pending.append(event)
                existing.add(key)
                self.indicator_events_detected += 1
        if not pending:
            return
        if not state.get("pending_indicator_deadline"):
            deadline = detected_at + timedelta(seconds=self.indicator_aggregation_seconds)
            generation = int(state.get("pending_indicator_generation") or 0) + 1
            state["pending_indicator_generation"] = generation
            state["pending_indicator_deadline"] = deadline.isoformat()
            heapq.heappush(
                self.pending_indicator_deadlines,
                (deadline.timestamp(), security_id, generation),
            )
        state["state"] = "EVENT_PENDING"

    def _indicator_safety_gates(
        self,
        state: Dict[str, Any],
        features: Dict[str, Any],
        direction: str,
        now: datetime,
    ) -> Tuple[List[str], Optional[float]]:
        failures: List[str] = []
        try:
            received_at = datetime.fromisoformat(str(features.get("received_at")))
        except (TypeError, ValueError):
            received_at = None
        if (
            received_at is None
            or (now - received_at).total_seconds() > self.config.intra_finder_data_stale_seconds
        ):
            failures.append("DATA_STALE")
        depth = features.get("depth") or []
        if len(depth) < 5:
            failures.append("DEPTH_INCOMPLETE")
        spread = features.get("spread_percent")
        if spread is None or float(spread) > self.config.intra_finder_max_spread_percent:
            failures.append("SPREAD_TOO_WIDE")
        price = float(features.get("last_price") or 0.0)
        slippage: Optional[float] = None
        if price <= 0:
            failures.append("INVALID_PRICE")
        elif depth:
            trade_amount = float(os.getenv("INTRA_FINDER_TRADE_AMOUNT", "100000"))
            sides = [direction] if direction in {"LONG", "SHORT"} else ["LONG", "SHORT"]
            estimates = [
                self._estimated_slippage(
                    depth,
                    direction=side,
                    reference_price=price,
                    trade_amount=trade_amount,
                )
                for side in sides
            ]
            valid_estimates = [float(value) for value in estimates if value is not None]
            slippage = max(valid_estimates) if valid_estimates else None
        if slippage is None or slippage > self.config.intra_finder_max_slippage_percent:
            failures.append("INSUFFICIENT_DEPTH_CAPACITY")
        if not features.get("connection_warm"):
            failures.append("CONNECTION_WARMING_UP")
        if now.time() >= dt_time(15, 0):
            failures.append("ENTRY_CUTOFF")
        upper = float(features.get("upper_circuit") or 0.0)
        lower = float(features.get("lower_circuit") or 0.0)
        if direction in {"LONG", "MIXED", "NEUTRAL"} and upper > 0 and price >= upper * 0.998:
            failures.append("UPPER_CIRCUIT_PROXIMITY")
        if direction in {"SHORT", "MIXED", "NEUTRAL"} and lower > 0 and price <= lower * 1.002:
            failures.append("LOWER_CIRCUIT_PROXIMITY")
        last_event = (self.event_state.get("last_stock_event_at") or {}).get(
            str(state["security_id"])
        )
        if last_event:
            try:
                elapsed = (now - datetime.fromisoformat(str(last_event))).total_seconds()
                if elapsed < self.stock_agent_cooldown_seconds:
                    failures.append("STOCK_AGENT_COOLDOWN")
            except ValueError:
                pass
        return failures, slippage

    def _create_indicator_event(
        self,
        stock: Dict[str, Any],
        state: Dict[str, Any],
        features: Dict[str, Any],
        indicator_events: List[Dict[str, Any]],
        direction: str,
        attention_score: float,
        now: datetime,
    ) -> Optional[Dict[str, Any]]:
        event_types = sorted({str(item.get("event_type")) for item in indicator_events})
        evidence_timestamps = sorted(
            {
                str(item.get("detected_at"))
                for item in indicator_events
                if item.get("detected_at")
            }
        )
        first_evidence = evidence_timestamps[0] if evidence_timestamps else now.isoformat()
        identity = "|".join(
            [
                self.market_time.market_date_str(),
                str(stock["isin"]),
                str(stock["exchange_segment"]),
                first_evidence,
                ",".join(event_types),
            ]
        )
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        if event_id in (self.event_state.get("events") or {}):
            self.events_suppressed += 1
            return None
        price = float(features["last_price"])
        event = SetupEvent(
            event_id=event_id,
            market_date=self.market_time.market_date_str(),
            universe_version=self.universe_version,
            isin=str(stock["isin"]),
            exchange_segment=str(stock["exchange_segment"]),
            security_id=int(stock["security_id"]),
            symbol=str(stock.get("symbol") or ""),
            direction=direction,
            setup_type="INDICATOR_EVENT",
            setup_state="TRIGGERED",
            setup_score=attention_score,
            payload={
                "display_name": stock.get("display_name"),
                "created_at": now.isoformat(),
                "instrument": stock.get("instrument", "EQUITY"),
                "price": price,
                "adv_20_cr": (stock.get("historical") or {}).get("adv_20_cr"),
                "atr_percent": (stock.get("historical") or {}).get("atr_percent"),
                "avg_volume_20": (stock.get("historical") or {}).get("avg_volume_20"),
                "historical": stock.get("historical"),
                "static_tradability": stock.get("tradability"),
                "selected_venue": {
                    "exchange": stock.get("exchange"),
                    "exchange_segment": stock.get("exchange_segment"),
                    "security_id": stock.get("security_id"),
                    "selected_venue_reason": stock.get("selected_venue_reason"),
                },
                "entry_zone": [round(price * 0.9995, 4), round(price * 1.0005, 4)],
                "invalidation_level": None,
                "opening_range": {
                    "high": state.get("opening_range_high"),
                    "low": state.get("opening_range_low"),
                },
                "vwap": features.get("vwap"),
                "relative_volume": features.get("relative_volume"),
                "volume_acceleration": features.get("volume_acceleration"),
                "spread": features.get("spread_percent"),
                "five_level_depth_summary": {
                    "best_bid": features.get("best_bid"),
                    "best_ask": features.get("best_ask"),
                    "bid_quantity": features.get("bid_quantity_5"),
                    "ask_quantity": features.get("ask_quantity_5"),
                    "imbalance": features.get("depth_imbalance"),
                    "order_count_imbalance": features.get("order_count_imbalance"),
                },
                "estimated_slippage": features.get("estimated_slippage_percent"),
                "trade_amount": float(os.getenv("INTRA_FINDER_TRADE_AMOUNT", "100000")),
                "data_quality": {"fresh": True, "depth_levels": len(features.get("depth") or [])},
                "score_components": {
                    "attention_priority": attention_score,
                    "indicator_event_count": len(indicator_events),
                },
                "indicator_events": indicator_events,
                "indicator_snapshot": state.get("indicator_snapshot") or {},
                "recent_closed_bars": list(state.get("minute_bars") or [])[-10:],
                "event_trigger_rule": "one_or_more_new_indicator_events",
                "evidence_timestamps": evidence_timestamps,
                "detector_schema_version": self.EVENT_STATE_SCHEMA_VERSION,
                "detector_mode": self.detector_mode,
                "latest_regime_context": self._load_context(self.config.regime_latest_path),
                "latest_nifty_context": self._load_context(self.config.nifty_depth_latest_path),
                "shadow_mode": self.shadow_mode,
            },
        ).as_dict()
        self.event_state.setdefault("events", {})[event_id] = {
            "event_id": event_id,
            "created_at": now.isoformat(),
            "indicator_events": event_types,
        }
        self.event_state.setdefault("last_stock_event_at", {})[
            str(stock["security_id"])
        ] = now.isoformat()
        StorageService.save_snapshot(
            self.config.stage2_event_state_path(self.market_time.market_date_str()),
            self.event_state,
        )
        StorageService.append_json_line(
            self.config.stage2_events_path(self.market_time.market_date_str()),
            event,
        )
        self.events_formed += 1
        self.indicator_aggregates_formed += 1
        state["state"] = "TRIGGERED"
        if not self.shadow_mode:
            self._dispatch_event(event)
        return event

    def _flush_due_indicator_events(self, now: datetime) -> List[Dict[str, Any]]:
        emitted: List[Dict[str, Any]] = []
        while self.pending_indicator_deadlines and self.pending_indicator_deadlines[0][0] <= now.timestamp():
            _, security_id, generation = heapq.heappop(self.pending_indicator_deadlines)
            state = self.states.get(security_id)
            stock = self.stocks_by_security_id.get(security_id)
            if not state or not stock:
                continue
            if generation != int(state.get("pending_indicator_generation") or 0):
                continue
            indicator_events = list(state.get("pending_indicator_events") or [])
            state["pending_indicator_events"] = []
            state["pending_indicator_deadline"] = None
            if not indicator_events:
                continue
            direction = self._indicator_direction(indicator_events)
            features = dict(state.get("latest_features") or {})
            failures, slippage = self._indicator_safety_gates(
                state, features, direction, now
            )
            self.gate_failure_counts.update(failures)
            if failures:
                state["state"] = "COOLDOWN" if "STOCK_AGENT_COOLDOWN" in failures else "WATCHING"
                self.events_suppressed += 1
                continue
            features["estimated_slippage_percent"] = slippage
            attention_score = self._indicator_attention_score(indicator_events)
            event = self._create_indicator_event(
                stock,
                state,
                features,
                indicator_events,
                direction,
                attention_score,
                now,
            )
            if event:
                self._log(
                    f"INDICATOR EVENT | {stock.get('symbol')} direction={direction} "
                    f"evidence={','.join(item['event_type'] for item in indicator_events)} "
                    f"priority={attention_score:.0f} price={float(features.get('last_price') or 0):.2f} "
                    f"shadow={self.shadow_mode}."
                )
                emitted.append(event)
        return emitted

    def process_packet(
        self,
        packet: Dict[str, Any],
        *,
        received_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        received_at = received_at or self.market_time.now()
        try:
            security_id = int(packet.get("security_id"))
        except (TypeError, ValueError):
            return None
        stock = self.stocks_by_security_id.get(security_id)
        state = self.states.get(security_id)
        price = self._number(packet, "LTP", "ltp", "last_price", "latest_traded_price")
        if not stock or state is None:
            return None
        self.packet_count += 1
        self.last_global_packet_at = received_at
        state["last_any_packet_at"] = received_at.isoformat()
        if state.get("first_packet_at") is None:
            state["first_packet_at"] = received_at.isoformat()
        self.received_security_ids.add(security_id)
        expected = len(self.stocks_by_security_id)
        if expected:
            milestones_logged = getattr(self, "coverage_milestones_logged", set())
            self.coverage_milestones_logged = milestones_logged
            coverage_percent = int(len(self.received_security_ids) * 100 / expected)
            for milestone in (25, 50, 75, 90, 100):
                if coverage_percent >= milestone and milestone not in milestones_logged:
                    milestones_logged.add(milestone)
                    self._log(
                        f"Feed coverage reached {milestone}%: "
                        f"{len(self.received_security_ids):,}/{expected:,} instruments observed."
                    )
        self.raw_buffer.append(
            {
                "received_at": received_at.isoformat(),
                "security_id": security_id,
                "exchange_segment": stock["exchange_segment"],
                "packet_json": json.dumps(packet, separators=(",", ":"), default=str),
            }
        )
        if price is None or price <= 0:
            self._flush_if_due()
            return None

        now_ts = received_at.timestamp()
        previous_price = state["last_price"]
        volume = self._number(packet, "volume", "total_volume") or float(state["day_volume"])
        self._record_volume(state, volume=volume, now_ts=now_ts)
        state["last_price"] = price
        state["last_packet_at"] = received_at.isoformat()
        self.full_packet_security_ids.add(security_id)
        self._update_opening_range(state, price, received_at)

        official_vwap = self._number(packet, "avg_price", "average_price", "ATP")
        if official_vwap and official_vwap > 0:
            state["vwap"] = official_vwap
        depth = self._depth(packet)
        depth_features = self._depth_features(depth, price)
        trade_amount = float(os.getenv("INTRA_FINDER_TRADE_AMOUNT", "100000"))
        direction_hint = "LONG" if float(depth_features["depth_imbalance"]) >= 0 else "SHORT"
        slippage = self._estimated_slippage(
            depth,
            direction=direction_hint,
            reference_price=price,
            trade_amount=trade_amount,
        )
        features = {
            "received_at": received_at.isoformat(),
            "last_price": price,
            "previous_price": previous_price,
            "price_change": (
                price - float(previous_price) if previous_price not in (None, 0) else 0.0
            ),
            "day_volume": volume,
            "vwap": state["vwap"],
            "opening_range_high": state["opening_range_high"],
            "opening_range_low": state["opening_range_low"],
            "relative_volume": self._relative_volume(stock, volume, received_at),
            "volume_acceleration": self._volume_acceleration(
                state["volume_deltas"],
                now_ts,
                state.get("volume_started_at"),
            ),
            "estimated_slippage_percent": slippage,
            "upper_circuit": (stock.get("tradability") or {}).get("upper_circuit"),
            "lower_circuit": (stock.get("tradability") or {}).get("lower_circuit"),
            "data_fresh": True,
            "connection_warm": bool(
                getattr(self, "connected_at", None)
                and (received_at - self.connected_at).total_seconds()
                >= self.config.intra_finder_reconnect_warmup_seconds
            ),
            "depth": depth,
            **depth_features,
        }
        state["latest_features"] = features
        second_key = received_at.replace(microsecond=0).isoformat()
        if state["last_second"] != second_key:
            state["last_second"] = second_key
            self.derived_buffer.append(
                {
                    "received_at": second_key,
                    "security_id": security_id,
                    "exchange_segment": stock["exchange_segment"],
                    "symbol": stock.get("symbol"),
                    **{key: value for key, value in features.items() if key != "depth"},
                }
            )
        indicator_events = self.indicator_engine.on_tick(
            state,
            timestamp=received_at,
            price=price,
            cumulative_volume=volume,
            vwap=float(state["vwap"]) if state.get("vwap") else None,
            opening_range_high=(
                float(state["opening_range_high"])
                if state.get("opening_range_high") is not None
                else None
            ),
            opening_range_low=(
                float(state["opening_range_low"])
                if state.get("opening_range_low") is not None
                else None
            ),
            opening_range_complete=bool(state.get("opening_range_complete")),
        )
        if indicator_events:
            self.candidates_seen += len(indicator_events)
            self._queue_indicator_evidence(
                security_id,
                state,
                indicator_events,
                received_at,
            )
        emitted = self._flush_due_indicator_events(received_at)
        self._flush_if_due()
        self._save_status_if_due()
        return emitted[-1] if emitted else None

    def _event_key(self, stock: Dict[str, Any], setup: str, direction: str, now: datetime) -> str:
        occurrence = int(now.timestamp()) // self.config.intra_finder_setup_cooldown_seconds
        return "|".join(
            [
                self.market_time.market_date_str(),
                str(stock["isin"]),
                str(stock["exchange_segment"]),
                setup,
                direction,
                str(occurrence),
            ]
        )

    def _active_setup_key(self, stock: Dict[str, Any], setup: str, direction: str) -> str:
        return "|".join(
            [
                self.market_time.market_date_str(),
                str(stock["isin"]),
                str(stock["exchange_segment"]),
                setup,
                direction,
            ]
        )

    def _update_active_setup_invalidations(
        self,
        stock: Dict[str, Any],
        state: Dict[str, Any],
        features: Dict[str, Any],
    ) -> None:
        active = self.event_state.setdefault("active_setups", {})
        price = float(features.get("last_price") or 0)
        vwap = float(features.get("vwap") or 0)
        high = float(state.get("opening_range_high") or 0)
        low = float(state.get("opening_range_low") or 0)
        changed = False
        prefix = "|".join(
            [
                self.market_time.market_date_str(),
                str(stock["isin"]),
                str(stock["exchange_segment"]),
            ]
        )
        for key, value in list(active.items()):
            if not key.startswith(prefix + "|") or not value.get("active"):
                continue
            setup = str(value.get("setup"))
            direction = str(value.get("direction"))
            invalidated = (
                (setup == "ORB" and direction == "LONG" and high > 0 and price <= high)
                or (setup == "ORB" and direction == "SHORT" and low > 0 and price >= low)
                or (
                    setup == "VWAP_RECLAIM_PULLBACK"
                    and direction == "LONG"
                    and vwap > 0
                    and price < vwap
                )
                or (
                    setup == "VWAP_RECLAIM_PULLBACK"
                    and direction == "SHORT"
                    and vwap > 0
                    and price > vwap
                )
            )
            if invalidated:
                value["active"] = False
                value["invalidated_at"] = features.get("received_at")
                changed = True
        if changed:
            StorageService.save_snapshot(
                self.config.stage2_event_state_path(self.market_time.market_date_str()),
                self.event_state,
            )

    def _load_context(self, path: Path) -> Optional[Dict[str, Any]]:
        payload = StorageService.load_snapshot(path)
        if not isinstance(payload, dict):
            return None
        compact: Dict[str, Any] = {
            "stage": payload.get("stage"),
            "generated_at_utc": payload.get("generated_at_utc"),
            "source_path": str(path),
        }
        if "regime" in payload:
            regime = payload.get("regime") or {}
            compact["regime"] = {
                key: regime.get(key)
                for key in (
                    "status",
                    "market_regime",
                    "confidence",
                    "index_regime",
                    "breadth_regime",
                    "volatility_regime",
                    "flow_regime",
                    "event_regime",
                    "new_trade_permission",
                    "participation_bias",
                    "max_position_size_multiplier",
                    "risk_flags",
                    "reasoning_summary",
                )
            }
        else:
            compact["summary"] = payload.get("summary")
            compact["targets"] = payload.get("targets")
            compact["latest_full_packet"] = payload.get("latest_full_packet")
            depth = payload.get("latest_depth_200") or {}
            compact["latest_depth_200"] = {
                "bid_summary": depth.get("bid_summary"),
                "ask_summary": depth.get("ask_summary"),
                "depth_imbalance": depth.get("depth_imbalance"),
            }
            compact["derived_signals"] = payload.get("derived_signals")
        return compact

    def _create_event(
        self,
        stock: Dict[str, Any],
        state: Dict[str, Any],
        features: Dict[str, Any],
        setup: str,
        direction: str,
        score: float,
        components: Dict[str, float],
        now: datetime,
    ) -> Optional[Dict[str, Any]]:
        key = self._event_key(stock, setup, direction, now)
        active_key = self._active_setup_key(stock, setup, direction)
        active_setup = (self.event_state.get("active_setups") or {}).get(active_key)
        if active_setup and active_setup.get("active"):
            marker = f"active:{active_key}:{active_setup.get('event_id')}"
            if state.get("last_suppressed_key") != marker:
                self.events_suppressed += 1
                state["last_suppressed_key"] = marker
            state["state"] = "COOLDOWN"
            return None
        prior = (self.event_state.get("events") or {}).get(key)
        if prior:
            marker = f"event:{key}"
            if state.get("last_suppressed_key") != marker:
                self.events_suppressed += 1
                state["last_suppressed_key"] = marker
            state["state"] = "COOLDOWN"
            return None
        event_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        price = float(features["last_price"])
        invalidation = (
            state["opening_range_high"] if setup == "ORB" and direction == "LONG"
            else state["opening_range_low"] if setup == "ORB"
            else features.get("vwap")
        )
        confirmation = state["confirmations"].get(f"{setup}:{direction}") or {}
        evidence_epoch_values = [
            confirmation.get("first_seen_at"),
            confirmation.get("last_seen_at"),
        ]
        if setup == "ORB":
            evidence_epoch_values.append(
                (state.get("orb_break") or {}).get(direction, {}).get("crossed_at")
            )
        else:
            flow = (state.get("vwap_reclaim") or {}).get(direction, {})
            evidence_epoch_values.extend(
                [flow.get("reclaimed_at"), flow.get("pullback_at")]
            )
        evidence_timestamps = sorted(
            {
                datetime.fromtimestamp(float(value), tz=self.market_time.tz).isoformat()
                for value in evidence_epoch_values
                if value is not None
            }
        )
        if features["received_at"] not in evidence_timestamps:
            evidence_timestamps.append(features["received_at"])
        event = SetupEvent(
            event_id=event_id,
            market_date=self.market_time.market_date_str(),
            universe_version=self.universe_version,
            isin=str(stock["isin"]),
            exchange_segment=str(stock["exchange_segment"]),
            security_id=int(stock["security_id"]),
            symbol=str(stock.get("symbol") or ""),
            direction=direction,
            setup_type=setup,
            setup_state="TRIGGERED",
            setup_score=score,
            payload={
                "display_name": stock.get("display_name"),
                "instrument": stock.get("instrument", "EQUITY"),
                "price": price,
                "adv_20_cr": (stock.get("historical") or {}).get("adv_20_cr"),
                "atr_percent": (stock.get("historical") or {}).get("atr_percent"),
                "avg_volume_20": (stock.get("historical") or {}).get("avg_volume_20"),
                "historical": stock.get("historical"),
                "static_tradability": stock.get("tradability"),
                "selected_venue": {
                    "exchange": stock.get("exchange"),
                    "exchange_segment": stock.get("exchange_segment"),
                    "security_id": stock.get("security_id"),
                    "selected_venue_reason": stock.get("selected_venue_reason"),
                },
                "entry_zone": [round(price * 0.9995, 4), round(price * 1.0005, 4)],
                "invalidation_level": invalidation,
                "opening_range": {
                    "high": state["opening_range_high"],
                    "low": state["opening_range_low"],
                },
                "vwap": features.get("vwap"),
                "relative_volume": features.get("relative_volume"),
                "volume_acceleration": features.get("volume_acceleration"),
                "spread": features.get("spread_percent"),
                "five_level_depth_summary": {
                    "best_bid": features.get("best_bid"),
                    "best_ask": features.get("best_ask"),
                    "bid_quantity": features.get("bid_quantity_5"),
                    "ask_quantity": features.get("ask_quantity_5"),
                    "imbalance": features.get("depth_imbalance"),
                    "order_count_imbalance": features.get("order_count_imbalance"),
                },
                "estimated_slippage": features.get("estimated_slippage_percent"),
                "trade_amount": float(os.getenv("INTRA_FINDER_TRADE_AMOUNT", "100000")),
                "data_quality": {"fresh": True, "depth_levels": len(features.get("depth") or [])},
                "score_components": components,
                "evidence_timestamps": evidence_timestamps,
                "detector_schema_version": self.EVENT_STATE_SCHEMA_VERSION,
                "latest_regime_context": self._load_context(self.config.regime_latest_path),
                "latest_nifty_context": self._load_context(self.config.nifty_depth_latest_path),
                "shadow_mode": self.shadow_mode,
            },
        ).as_dict()
        self.event_state.setdefault("events", {})[key] = {
            "event_id": event_id,
            "created_at": now.isoformat(),
        }
        self.event_state.setdefault("active_setups", {})[active_key] = {
            "active": True,
            "setup": setup,
            "direction": direction,
            "event_id": event_id,
            "created_at": now.isoformat(),
        }
        StorageService.save_snapshot(
            self.config.stage2_event_state_path(self.market_time.market_date_str()),
            self.event_state,
        )
        StorageService.append_json_line(
            self.config.stage2_events_path(self.market_time.market_date_str()),
            event,
        )
        self.events_formed += 1
        state["last_suppressed_key"] = None
        state["state"] = "TRIGGERED"
        if not self.shadow_mode:
            self._dispatch_event(event)
        return event

    def _dispatch_event(self, event: Dict[str, Any]) -> None:
        with self.dispatch_lock:
            self.agent_futures = {future for future in self.agent_futures if not future.done()}
            if len(self.agent_futures) >= self.config.intra_finder_agent_concurrency:
                self.pending_agent_events.append(event)
                self.pending_agent_events.sort(
                    key=lambda item: (
                        float(item.get("setup_score") or 0),
                        str(item.get("created_at") or ""),
                    ),
                    reverse=True,
                )
                if len(self.pending_agent_events) > self.agent_queue_max:
                    self.pending_agent_events.pop()
                    self.agent_queue_overflow_dropped += 1
                return
            self._submit_agent_event_locked(event)

    def _event_dispatch_age_seconds(self, event: Dict[str, Any], now: datetime) -> float:
        timestamps = event.get("evidence_timestamps") or []
        reference = event.get("created_at") or (timestamps[-1] if timestamps else None)
        try:
            return max(0.0, (now - datetime.fromisoformat(str(reference))).total_seconds())
        except (TypeError, ValueError):
            return float("inf")

    def _next_fresh_agent_event_locked(self) -> Optional[Dict[str, Any]]:
        now = self.market_time.now()
        while self.pending_agent_events:
            event = self.pending_agent_events.pop(0)
            if self._event_dispatch_age_seconds(event, now) <= self.agent_queue_max_age_seconds:
                return event
            self.agent_queue_expired += 1
        return None

    def _submit_agent_event_locked(self, event: Dict[str, Any]) -> None:
        future = self.executor.submit(self._post_agent_event, event)
        self.agent_futures.add(future)
        self.events_triggered += 1
        future.add_done_callback(self._agent_event_done)

    def _agent_event_done(self, future: Future) -> None:
        with self.dispatch_lock:
            self.agent_futures.discard(future)
            try:
                future.result()
                self.agent_dispatch_successes += 1
            except Exception as exc:
                self.agent_dispatch_failures += 1
                print(f"Intra-Finder agent dispatch failed: {type(exc).__name__}.")
            next_event = self._next_fresh_agent_event_locked()
            if next_event is not None:
                self._submit_agent_event_locked(next_event)

    def _post_agent_event(self, event: Dict[str, Any]) -> None:
        endpoint = os.getenv(
            "AI_TRADING_EVENT_URL",
            "http://ai-trading-agents:8020/ai-trading/event",
        )
        headers = {"Content-Type": "application/json"}
        token = os.getenv("AI_TRADING_BACKEND_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.post(endpoint, json=event, headers=headers, timeout=10)
        response.raise_for_status()

    def _write_parquet(self, directory: Path, prefix: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.parquet"
        frame = pd.DataFrame(rows)
        frame.to_parquet(path, index=False, compression="zstd")

    def _submit_io(self, function: Any, *args: Any) -> None:
        executor = getattr(self, "io_executor", None)
        if executor is None:
            function(*args)
            return
        self.io_futures = {future for future in self.io_futures if not future.done()}
        future = executor.submit(function, *args)
        self.io_futures.add(future)

    def _persist_buffers(
        self,
        raw: List[Dict[str, Any]],
        derived: List[Dict[str, Any]],
        checkpoint: Dict[str, Any],
    ) -> None:
        base = self.config.stage2_results_dir / self.market_time.market_date_str()
        for rows, directory_name, prefix in (
            (raw, "raw-depth", "packets"),
            (derived, "one-second", "snapshots"),
        ):
            grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in rows:
                try:
                    hour = datetime.fromisoformat(str(row["received_at"])).strftime("%H")
                except (KeyError, TypeError, ValueError):
                    hour = self.market_time.now().strftime("%H")
                grouped[hour].append(row)
            for hour, hour_rows in grouped.items():
                self._write_parquet(base / directory_name / f"hour={hour}", prefix, hour_rows)
        StorageService.save_snapshot(
            self.config.stage2_runtime_state_path(self.market_time.market_date_str()),
            checkpoint,
        )

    def flush(self) -> None:
        if not self.raw_buffer and not self.derived_buffer:
            return
        raw, derived = self.raw_buffer, self.derived_buffer
        self.raw_buffer, self.derived_buffer = [], []
        checkpoint = self._runtime_state_payload()
        self._submit_io(self._persist_buffers, raw, derived, checkpoint)
        self.last_flush = time.time()

    def _flush_if_due(self) -> None:
        if time.time() - self.last_flush >= self.config.intra_finder_flush_seconds:
            self.flush()

    def _save_status_if_due(self, *, force: bool = False) -> None:
        if (
            not force
            and time.time() - self.last_status_save < self.config.intra_finder_status_seconds
        ):
            return
        now = self.market_time.now()
        stale_before = now - timedelta(seconds=self.config.intra_finder_data_stale_seconds)
        stale = 0
        active = 0
        stock_states = []
        for security_id, state in self.states.items():
            received = state.get("last_packet_at")
            try:
                received_dt = datetime.fromisoformat(received) if received else None
            except ValueError:
                received_dt = None
            if not received_dt or received_dt < stale_before:
                stale += 1
                if received_dt:
                    state["state"] = "DATA_STALE"
                elif state.get("state") not in {"SESSION_ENDED", "WARMING_UP"}:
                    state["state"] = "WAITING_FOR_DATA"
            else:
                active += 1
            stock_states.append(
                {
                    "security_id": security_id,
                    "symbol": self.stocks_by_security_id[security_id].get("symbol"),
                    "exchange_segment": self.stocks_by_security_id[security_id].get("exchange_segment"),
                    "state": state["state"],
                    "last_packet_at": received,
                    "features": {
                        key: value
                        for key, value in state["latest_features"].items()
                        if key != "depth"
                    },
                    "indicator_snapshot": state.get("indicator_snapshot") or {},
                    "pending_indicator_events": [
                        item.get("event_type")
                        for item in (state.get("pending_indicator_events") or [])
                    ],
                }
            )
        global_packet_age = (
            max(0.0, (now - self.last_global_packet_at).total_seconds())
            if self.last_global_packet_at
            else None
        )
        status = (
            "recording"
            if self.connection_state == "CONNECTED"
            and (
                global_packet_age is None
                or global_packet_age <= self.config.intra_finder_global_idle_seconds
            )
            else "degraded"
        )
        summary = {
            "status": status,
            "market_date": self.market_time.market_date_str(),
            "universe_version": self.universe_version,
            "expected_instruments": len(self.stocks_by_security_id),
            "requested_instruments": len(self.stocks_by_security_id),
            "subscribed_instruments": len(self.received_security_ids),
            "observed_instruments": len(self.received_security_ids),
            "full_packet_instruments": len(self.full_packet_security_ids),
            "quote_verified_instruments": len(self.quote_verified_security_ids),
            "covered_instruments": len(
                self.received_security_ids | self.quote_verified_security_ids
            ),
            "active_instruments": active,
            "packet_count": self.packet_count,
            "reconnect_count": self.reconnect_count,
            "universe_wait_count": self.universe_wait_count,
            "stale_instruments": stale,
            "quiet_instruments": stale,
            "connection_state": self.connection_state,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_global_packet_at": (
                self.last_global_packet_at.isoformat() if self.last_global_packet_at else None
            ),
            "global_packet_age_seconds": (
                round(global_packet_age, 3) if global_packet_age is not None else None
            ),
            "last_connection_error": self.last_connection_error,
            "session_state": self.session_state,
            "opening_range_complete": sum(
                bool(state.get("opening_range_complete")) for state in self.states.values()
            ),
            "opening_range_recovery": {
                "requested": self.opening_range_recovery_requested,
                "completed": self.opening_range_recovery_completed,
                "failed": self.opening_range_recovery_failed,
            },
            "rvol_available": sum(
                (state.get("latest_features") or {}).get("relative_volume") is not None
                for state in self.states.values()
            ),
            "events_formed": self.events_formed,
            "events_triggered": self.events_triggered,
            "events_suppressed": self.events_suppressed,
            "detector_mode": self.detector_mode,
            "indicator_events_detected": self.indicator_events_detected,
            "indicator_aggregates_formed": self.indicator_aggregates_formed,
            "pending_indicator_stocks": sum(
                bool(state.get("pending_indicator_events")) for state in self.states.values()
            ),
            "agent_dispatch_active": len(self.agent_futures),
            "agent_dispatch_queued": len(self.pending_agent_events),
            "agent_dispatch_successes": self.agent_dispatch_successes,
            "agent_dispatch_failures": self.agent_dispatch_failures,
            "agent_queue_expired": self.agent_queue_expired,
            "agent_queue_overflow_dropped": self.agent_queue_overflow_dropped,
            "shadow_mode": self.shadow_mode,
        }
        self._log_progress(summary, force=force)
        payload = StorageService.build_payload("intra_finder", summary, "stocks", stock_states)
        self._submit_io(self._persist_status, payload)
        self.last_status_save = time.time()

    def _persist_status(self, payload: Dict[str, Any]) -> None:
        StorageService.save_snapshot(
            self.config.stage2_daily_path(self.market_time.market_date_str()),
            payload,
        )
        StorageService.save_snapshot(self.config.stage2_latest_path, payload)

    def health_payload(self) -> Tuple[bool, Dict[str, Any]]:
        now = self.market_time.now()
        session = self.market_calendar.session_status()
        age = (
            max(0.0, (now - self.last_global_packet_at).total_seconds())
            if self.last_global_packet_at
            else None
        )
        if self.connection_state == "WAITING_FOR_START" and session.is_before_open:
            healthy = True
            reason = "waiting_for_configured_start"
        elif not self.universe_version:
            healthy = False
            reason = "universe_unavailable"
        elif session.is_before_open:
            healthy = self.connection_state in {"CONNECTED", "WAITING_FOR_START"}
            reason = "preopen"
        elif session.is_after_close:
            healthy = True
            reason = "session_ended"
        elif self.connection_state != "CONNECTED":
            healthy = False
            reason = "feed_disconnected"
        elif age is None or age > self.config.intra_finder_global_idle_seconds:
            healthy = False
            reason = "global_packet_idle"
        else:
            healthy = True
            reason = "live"
        return healthy, {
            "status": "healthy" if healthy else "unhealthy",
            "reason": reason,
            "market_date": self.market_time.market_date_str(),
            "universe_version": self.universe_version,
            "connection_state": self.connection_state,
            "expected_instruments": len(self.stocks_by_security_id),
            "observed_instruments": len(self.received_security_ids),
            "full_packet_instruments": len(self.full_packet_security_ids),
            "quote_verified_instruments": len(self.quote_verified_security_ids),
            "covered_instruments": len(
                self.received_security_ids | self.quote_verified_security_ids
            ),
            "last_global_packet_at": (
                self.last_global_packet_at.isoformat() if self.last_global_packet_at else None
            ),
            "global_packet_age_seconds": round(age, 3) if age is not None else None,
            "reconnect_count": self.reconnect_count,
            "shadow_mode": self.shadow_mode,
            "detector_mode": self.detector_mode,
            "indicator_events_detected": self.indicator_events_detected,
            "indicator_aggregates_formed": self.indicator_aggregates_formed,
            "agent_dispatch_active": len(self.agent_futures),
            "agent_dispatch_queued": len(self.pending_agent_events),
            "agent_queue_expired": self.agent_queue_expired,
            "agent_queue_overflow_dropped": self.agent_queue_overflow_dropped,
        }

    def enforce_retention(self) -> None:
        root = self.config.stage2_results_dir.resolve()
        if root.name != "stage2" or self.config.results_dir.resolve() not in root.parents:
            raise RuntimeError(f"Refusing retention cleanup outside Stage 2 results: {root}")
        today = self.market_time.now().date()
        for date_dir in root.iterdir() if root.exists() else []:
            if not date_dir.is_dir():
                continue
            try:
                market_date = datetime.strptime(date_dir.name, "%Y-%m-%d").date()
            except ValueError:
                continue
            age = (today - market_date).days
            if age > self.config.intra_finder_raw_retention_days:
                raw = date_dir / "raw-depth"
                if raw.exists():
                    shutil.rmtree(raw)
            if age > self.config.intra_finder_derived_retention_days:
                derived = date_dir / "one-second"
                if derived.exists():
                    shutil.rmtree(derived)

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
        try:
            disconnect = getattr(feed, "disconnect", None)
            if disconnect is not None:
                result = disconnect()
                if asyncio.iscoroutine(result):
                    feed.loop.run_until_complete(result)
                return
        except Exception:
            pass
        try:
            close = getattr(feed, "close_connection", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    feed.loop.run_until_complete(result)
        except Exception:
            pass

    def _mark_session_ended(self) -> None:
        self.session_state = "SESSION_ENDED"
        self.connection_state = "SESSION_ENDED"
        for state in self.states.values():
            state["state"] = "SESSION_ENDED"
        self.flush()
        self._save_status_if_due(force=True)

    def run_forever(self) -> None:
        while True:
            feed = None
            try:
                session = self.market_calendar.session_status()
                if not session.is_trading_day:
                    self.session_state = "MARKET_CLOSED"
                    self.connection_state = "WAITING_FOR_TRADING_DAY"
                    print(f"Intra-Finder idle: {session.reason}")
                    time.sleep(300)
                    continue
                start_time = datetime.strptime(
                    self.config.intra_finder_start_time,
                    "%H:%M",
                ).time()
                if self.market_time.now().time() < start_time:
                    self.session_state = "PREOPEN"
                    self.connection_state = "WAITING_FOR_START"
                    time.sleep(30)
                    continue
                if session.is_after_close:
                    self._mark_session_ended()
                    time.sleep(300)
                    continue
                stocks = self.load_universe()
                instruments = self.build_instruments(stocks)
                batches = subscription_batches(instruments)
                print(
                    f"Intra-Finder subscribing to {len(instruments)} stocks in "
                    f"{len(batches)} subscription batch(es)."
                )
                self._log(
                    f"Starting Full Packet feed for universe={self.universe_version}; "
                    f"instruments={len(instruments):,}; detector={self.detector_mode}; "
                    f"aggregation={self.indicator_aggregation_seconds}s; shadow_mode={self.shadow_mode}."
                )
                # DhanHQ's v2 MarketFeed accepts the full list and performs the
                # protocol-level subscription batching on one socket.
                feed = self.dhan.build_marketfeed(instruments)
                credential_version = self.dhan.credential_version
                feed.run_forever()
                self.dhan.configure_marketfeed_websocket(feed)
                self.current_feed = feed
                self.received_security_ids.clear()
                self.full_packet_security_ids.clear()
                self.quote_verified_security_ids.clear()
                self.connection_generation += 1
                self.last_global_packet_at = None
                self.connected_at = self.market_time.now()
                self.connection_state = "CONNECTED"
                self.session_state = "PREOPEN" if session.is_before_open else "LIVE"
                self.last_connection_error = None
                self._start_opening_range_recovery()
                last_session_check = time.monotonic()
                while True:
                    if self.dhan.reload_credentials_if_changed() or self.dhan.credential_version != credential_version:
                        raise RuntimeError("credential_rotated")
                    if time.monotonic() - last_session_check >= 30:
                        current_session = self.market_calendar.session_status()
                        if current_session.is_after_close:
                            raise SessionEnded("market_session_ended")
                        if self._universe_version_changed():
                            raise RuntimeError("universe_rotated")
                        self.session_state = (
                            "PREOPEN" if current_session.is_before_open else "LIVE"
                        )
                        self._start_opening_range_recovery()
                        self._start_coverage_verification()
                        last_session_check = time.monotonic()
                    packet = self._get_feed_data(feed)
                    if isinstance(packet, dict):
                        self.process_packet(packet)
            except SessionEnded:
                self._close_feed(feed)
                self.current_feed = None
                self._mark_session_ended()
                time.sleep(300)
            except (FileNotFoundError, RuntimeError) as exc:
                if isinstance(exc, FileNotFoundError) or "Universe Scanner" in str(exc):
                    self.universe_wait_count += 1
                    self.connection_state = "WAITING_FOR_UNIVERSE"
                    self.last_connection_error = type(exc).__name__
                    if self.universe_wait_count == 1 or self.universe_wait_count % 12 == 0:
                        print(f"Intra-Finder waiting for Universe Scanner: {type(exc).__name__}.")
                    time.sleep(5)
                    continue
                self.reconnect_count += 1
                self.connection_state = "RECONNECTING"
                self.last_connection_error = type(exc).__name__
                print(f"Intra-Finder reconnecting: {type(exc).__name__}.")
                self.flush()
                self._save_status_if_due(force=True)
                self._close_feed(feed)
                self.current_feed = None
                time.sleep(5)
            except Exception as exc:
                self.reconnect_count += 1
                self.connection_state = "RECONNECTING"
                self.last_connection_error = type(exc).__name__
                print(f"Intra-Finder reconnecting: {type(exc).__name__}.")
                self.flush()
                self._save_status_if_due(force=True)
                self._close_feed(feed)
                self.current_feed = None
                time.sleep(5)

    def close(self) -> None:
        self._close_feed(getattr(self, "current_feed", None))
        self.flush()
        self._save_status_if_due(force=True)
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.recovery_executor.shutdown(wait=False, cancel_futures=True)
        self.io_executor.shutdown(wait=True, cancel_futures=False)
