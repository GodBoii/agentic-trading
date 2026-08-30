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
from statistics import median
from threading import RLock, Thread, current_thread
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
from dhanhq import MarketFeed

from pipeline.config import PipelineConfig
from pipeline.models import SetupEvent
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.market_calendar_service import MarketCalendarService
from pipeline.services.process_memory_service import release_unused_process_memory
from pipeline.services.storage_service import StorageService


from pipeline.stages.live_state import LiveStockState, OHLCV
from pipeline.stages.activity_ranker import ActivityRanker
from pipeline.stages.setups.momentum import MomentumSetup
from pipeline.stages.setups.mean_reversion import MeanReversionSetup



def subscription_batches(instruments: List[tuple], size: int = 100) -> List[List[tuple]]:
    if size <= 0:
        raise ValueError("subscription batch size must be positive")
    return [instruments[index : index + size] for index in range(0, len(instruments), size)]


class FeedIdleTimeout(RuntimeError):
    pass


class SessionEnded(RuntimeError):
    pass


class IntraFinder:
    EVENT_STATE_SCHEMA_VERSION = 6
    RUNTIME_STATE_SCHEMA_VERSION = 5

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
        self.released_session_date: Optional[str] = None
        self.state_lock = RLock()
        self.dispatch_lock = RLock()
        self.current_feed: Any = None
        self.io_executor = ThreadPoolExecutor(max_workers=1)
        self.io_futures: set[Future] = set()
        self.recovery_executor = ThreadPoolExecutor(max_workers=4)
        self.recovery_futures: set[Future] = set()
        self.opening_range_recovery_started = False
        self.opening_range_recovery_requested = 0
        self.opening_range_recovery_completed = 0
        self.opening_range_recovery_failed = 0
        self.agent_threads: set[Thread] = set()
        self.agent_dispatch_successes = 0
        self.agent_dispatch_failures = 0
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
        self.activity_ranker = ActivityRanker(self.market_time)
        self.setups = {}
        self.last_rank_time = 0.0
        self.pending_indicator_deadlines: List[Tuple[float, int, int]] = []
        self.indicator_events_detected = 0
        self.indicator_aggregates_formed = 0
        self.readiness_evaluations = 0
        self.readiness_passed = 0
        self.readiness_rechecks = 0
        self.readiness_threshold = float(
            os.getenv(
                "INTRA_FINDER_READINESS_SCORE_THRESHOLD",
                str(self.config.intra_finder_readiness_score_threshold),
            )
        )
        self.readiness_direction_margin = float(
            os.getenv(
                "INTRA_FINDER_READINESS_DIRECTION_MARGIN",
                str(self.config.intra_finder_readiness_direction_margin),
            )
        )
        self.readiness_min_completed_bars = max(
            15,
            int(
                os.getenv(
                    "INTRA_FINDER_READINESS_MIN_COMPLETED_BARS",
                    str(self.config.intra_finder_readiness_min_completed_bars),
                )
            ),
        )
        self.readiness_min_room_atr = max(
            0.0,
            float(
                os.getenv(
                    "INTRA_FINDER_READINESS_MIN_ROOM_ATR",
                    str(self.config.intra_finder_readiness_min_room_atr),
                )
            ),
        )
        self.readiness_max_last_trade_age_seconds = max(
            1,
            int(
                os.getenv(
                    "INTRA_FINDER_READINESS_MAX_LAST_TRADE_AGE_SECONDS",
                    str(self.config.intra_finder_readiness_max_last_trade_age_seconds),
                )
            ),
        )
        self.readiness_observation_seconds = max(
            60,
            int(
                os.getenv(
                    "INTRA_FINDER_READINESS_OBSERVATION_SECONDS",
                    str(self.config.intra_finder_readiness_observation_seconds),
                )
            ),
        )
        self.readiness_reevaluation_seconds = max(
            15,
            int(
                os.getenv(
                    "INTRA_FINDER_READINESS_REEVALUATION_SECONDS",
                    str(self.config.intra_finder_readiness_reevaluation_seconds),
                )
            ),
        )
        self.readiness_min_confirmation_seconds = max(
            0,
            int(
                os.getenv(
                    "INTRA_FINDER_READINESS_MIN_CONFIRMATION_SECONDS",
                    str(self.config.intra_finder_readiness_min_confirmation_seconds),
                )
            ),
        )
        self.readiness_max_entry_drift_atr = max(
            0.0,
            float(
                os.getenv(
                    "INTRA_FINDER_READINESS_MAX_ENTRY_DRIFT_ATR",
                    str(self.config.intra_finder_readiness_max_entry_drift_atr),
                )
            ),
        )

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
            f"readiness={summary['readiness_passed']:,}/{summary['readiness_evaluations']:,} "
            f"rechecks={summary['readiness_rechecks']:,} "
            f"pending={summary['pending_indicator_stocks']:,} events={summary['events_formed']:,} "
            f"agent_active={summary['agent_dispatch_active']:,} "
            f"dispatch_ok={summary['agent_dispatch_successes']:,} dispatch_failed={summary['agent_dispatch_failures']:,} "
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
                self.readiness_evaluations = 0
                self.readiness_passed = 0
                self.readiness_rechecks = 0
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

    def _new_state(self, stock: Dict[str, Any]) -> LiveStockState:
        adv = float(stock.get("historical", {}).get("adv") or 0.0)
        atr = float(stock.get("historical", {}).get("atr") or 0.0)
        baselines = stock.get("intraday_baselines", {}).get("volumes", {})
        median_vols = {k: int(v) for k, v in baselines.items()}
        
        state = LiveStockState(
            security_id=int(stock["security_id"]),
            exchange_segment=stock["exchange_segment"],
            symbol=stock.get("symbol", ""),
            adv=adv,
            historical_atr=atr,
            median_time_volumes=median_vols,
            previous_close=float(stock.get("historical", {}).get("previous_close") or 0.0)
        )
        self.setups[state.security_id] = [MomentumSetup(), MeanReversionSetup()]
        return state

    @staticmethod
    def _state_checkpoint_fields() -> Tuple[str, ...]:
        return ()

    def _runtime_state_payload(
        self,
        market_date: Optional[str] = None,
    ) -> Dict[str, Any]:
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
            "market_date": market_date or self.market_time.market_date_str(),
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
            "depth_samples",
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
                if key == "depth_samples":
                    value = deque(
                        (
                            (
                                float(item[0]),
                                float(item[1]),
                                float(item[2]),
                                float(item[3]),
                            )
                            for item in (value or [])
                            if isinstance(item, (list, tuple)) and len(item) == 4
                        ),
                        maxlen=120,
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

    @staticmethod
    def _packet_last_trade_at(packet: Dict[str, Any], received_at: datetime) -> Optional[datetime]:
        raw = packet.get("LTT") or packet.get("last_trade_time") or packet.get("last_traded_time")
        if raw in (None, ""):
            return None
        text = str(raw).strip()
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=received_at.tzinfo)
            return parsed.astimezone(received_at.tzinfo) if received_at.tzinfo else parsed
        except ValueError:
            pass
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(text, pattern).time()
            except ValueError:
                continue
            return received_at.replace(
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=parsed_time.second,
                microsecond=0,
            )
        return None

    @staticmethod
    def _update_depth_history(
        state: Dict[str, Any],
        *,
        timestamp: float,
        depth_features: Dict[str, Any],
    ) -> Dict[str, Any]:
        samples: Deque[Tuple[float, float, float, float]] = state.setdefault(
            "depth_samples", deque(maxlen=120)
        )
        samples.append(
            (
                timestamp,
                float(depth_features.get("depth_imbalance") or 0.0),
                float(depth_features.get("order_count_imbalance") or 0.0),
                float(depth_features.get("spread_percent") or 0.0),
            )
        )
        cutoff = timestamp - 30.0
        while samples and samples[0][0] < cutoff:
            samples.popleft()
        imbalances = [item[1] for item in samples]
        order_imbalances = [item[2] for item in samples]
        positive_ratio = (
            sum(value > 0 for value in imbalances) / len(imbalances) if imbalances else 0.0
        )
        return {
            "depth_imbalance_median_30s": median(imbalances) if imbalances else None,
            "order_count_imbalance_median_30s": median(order_imbalances) if order_imbalances else None,
            "depth_positive_ratio_30s": positive_ratio,
            "depth_sample_count_30s": len(imbalances),
        }

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
        
        if price is None or price <= 0:
            return None

        # Update state
        volume = self._number(packet, "volume", "total_volume") or 0.0
        state.latest_price = price
        state.cumulative_volume = int(volume)
        state.update_session_extremes(price)
        
        official_vwap = self._number(packet, "avg_price", "average_price", "ATP")
        if official_vwap and official_vwap > 0:
            state.session_vwap = official_vwap
            
        # Update rolling ranges placeholder logic
        state.rolling_1m_high = max(state.rolling_1m_high, price) if state.rolling_1m_high else price
        state.rolling_1m_low = min(state.rolling_1m_low, price) if state.rolling_1m_low else price
        state.rolling_5m_high = max(state.rolling_5m_high, price) if state.rolling_5m_high else price
        state.rolling_5m_low = min(state.rolling_5m_low, price) if state.rolling_5m_low else price

        # Process ranking every 5 seconds
        now_ts = received_at.timestamp()
        if now_ts - self.last_rank_time >= 5.0:
            self.activity_ranker.rank(self.states)
            self.last_rank_time = now_ts

        # Run setup machines if stock is hot
        if state.is_hot:
            for setup in self.setups.get(state.security_id, []):
                setup.evaluate(state)
                if setup.state.name == "TRIGGERED" and not getattr(setup, "dispatched", False):
                    # Valid setup triggered!
                    depth = self._depth(packet)
                    direction_hint = setup.direction
                    slippage = self._estimated_slippage(depth, direction_hint, price, price)
                    
                    if slippage <= 0.002: # 0.20% slippage gate
                        contract = setup.to_contract(state)
                        contract["isin"] = stock["isin"]
                        contract["security_id"] = state.security_id
                        contract["symbol"] = state.symbol
                        contract["exchange_segment"] = state.exchange_segment
                        contract["market_date"] = self.market_time.market_date_str()
                        setup.dispatched = True
                        self._dispatch_event(contract)
                        return contract

        self._flush_if_due()
        self._save_status_if_due()
        return None

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

    def _dispatch_event(self, event: Dict[str, Any]) -> None:
        """Dispatch event via bounded thread pool."""
        executor = getattr(self, "dispatch_executor", None)
        if executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self.dispatch_executor = ThreadPoolExecutor(max_workers=4)
            executor = self.dispatch_executor
        
        executor.submit(self._post_agent_event_immediately, event)
        with self.dispatch_lock:
            self.events_triggered += 1

    def _post_agent_event_immediately(self, event: Dict[str, Any]) -> None:
        try:
            self._post_agent_event(event)
            with self.dispatch_lock:
                self.agent_dispatch_successes += 1
        except Exception as exc:
            with self.dispatch_lock:
                self.agent_dispatch_failures += 1
            print(f"Intra-Finder agent dispatch failed: {type(exc).__name__}.")
        finally:
            with self.dispatch_lock:
                self.agent_threads.discard(current_thread())

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
        market_date: str,
    ) -> None:
        base = self.config.stage2_results_dir / market_date
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
            self.config.stage2_runtime_state_path(market_date),
            checkpoint,
        )

    def flush(
        self,
        *,
        force_checkpoint: bool = False,
        checkpoint_market_date: Optional[str] = None,
    ) -> None:
        if not self.raw_buffer and not self.derived_buffer:
            if force_checkpoint and self.states:
                self._submit_io(
                    StorageService.save_snapshot,
                    self.config.stage2_runtime_state_path(
                        checkpoint_market_date or self.market_time.market_date_str()
                    ),
                    self._runtime_state_payload(checkpoint_market_date),
                )
            return
        raw, derived = self.raw_buffer, self.derived_buffer
        self.raw_buffer, self.derived_buffer = [], []
        checkpoint = self._runtime_state_payload(checkpoint_market_date)
        market_date = checkpoint_market_date or self.market_time.market_date_str()
        self._submit_io(
            self._persist_buffers,
            raw,
            derived,
            checkpoint,
            market_date,
        )
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
            "readiness_evaluations": getattr(self, "readiness_evaluations", 0),
            "readiness_passed": getattr(self, "readiness_passed", 0),
            "readiness_rechecks": getattr(self, "readiness_rechecks", 0),
            "readiness_threshold": getattr(self, "readiness_threshold", None),
            "pending_indicator_stocks": sum(
                bool(state.get("pending_indicator_events")) for state in self.states.values()
            ),
            "agent_dispatch_active": len(self.agent_threads),
            "agent_dispatch_successes": self.agent_dispatch_successes,
            "agent_dispatch_failures": self.agent_dispatch_failures,
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
        if not session.is_trading_day:
            healthy = True
            reason = session.reason or "non_trading_day"
        elif self.connection_state == "WAITING_FOR_START" and session.is_before_open:
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
            "agent_dispatch_active": len(self.agent_threads),
            "agent_dispatch_successes": self.agent_dispatch_successes,
            "agent_dispatch_failures": self.agent_dispatch_failures,
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

    def _mark_session_ended(self, market_date: str) -> None:
        self.session_state = "SESSION_ENDED"
        self.connection_state = "SESSION_ENDED"
        for state in self.states.values():
            state["state"] = "SESSION_ENDED"
        self.flush(
            force_checkpoint=True,
            checkpoint_market_date=market_date,
        )
        self._save_status_if_due(force=True)

    def _wait_for_pending_io(self) -> bool:
        for future in list(self.io_futures):
            try:
                future.result()
            except Exception as exc:
                self._log(
                    f"Final session persistence failed; retaining memory for retry: "
                    f"{type(exc).__name__}: {exc}"
                )
                return False
        self.io_futures.clear()
        return True

    def _release_session_memory(self, market_date: str) -> int:
        with self.state_lock:
            released_stock_count = len(self.states)
            self.states.clear()
            self.stocks_by_security_id.clear()
            self.universe_payload = {}
            self.universe_version = ""
            self.raw_buffer.clear()
            self.derived_buffer.clear()
            self.pending_indicator_deadlines.clear()
            self.event_state = {}

        self.received_security_ids.clear()
        self.full_packet_security_ids.clear()
        self.quote_verified_security_ids.clear()
        self.coverage_milestones_logged.clear()
        self.gate_failure_counts.clear()
        for future in self.recovery_futures:
            future.cancel()
        self.recovery_futures.clear()
        self.coverage_verification_future = None
        self.opening_range_recovery_started = False
        self.last_global_packet_at = None
        self.connected_at = None
        self.packet_count = 0
        self.reconnect_count = 0
        self.universe_wait_count = 0
        self.events_formed = 0
        self.events_triggered = 0
        self.events_suppressed = 0
        self.connection_generation = 0
        self.opening_range_recovery_requested = 0
        self.opening_range_recovery_completed = 0
        self.opening_range_recovery_failed = 0
        self.agent_dispatch_successes = 0
        self.agent_dispatch_failures = 0
        self.candidates_seen = 0
        self.indicator_events_detected = 0
        self.indicator_aggregates_formed = 0
        self.readiness_evaluations = 0
        self.readiness_passed = 0
        self.readiness_rechecks = 0
        self.released_session_date = market_date
        release_unused_process_memory()
        return released_stock_count

    def _finalize_and_release_session(self, market_date: str) -> None:
        if self.released_session_date == market_date:
            return
        self._mark_session_ended(market_date)
        if not self._wait_for_pending_io():
            return
        released_stock_count = self._release_session_memory(market_date)
        self._log(
            f"Session memory released for {market_date}; "
            f"cleared_states={released_stock_count:,}."
        )

    def run_forever(self) -> None:
        while True:
            feed = None
            try:
                session = self.market_calendar.session_status()
                if not session.is_trading_day:
                    if self.states:
                        previous_market_date = str(
                            (self.universe_payload.get("summary") or {}).get(
                                "market_date"
                            )
                            or session.market_date
                        )
                        self._finalize_and_release_session(previous_market_date)
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
                    self._finalize_and_release_session(session.market_date)
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
                self._finalize_and_release_session(
                    self.market_calendar.session_status().market_date
                )
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
        self.recovery_executor.shutdown(wait=False, cancel_futures=True)
        self.io_executor.shutdown(wait=True, cancel_futures=False)
