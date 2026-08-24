"""Short-lived historical candle cache for stocks approaching an agent signal."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class SignalDataCacheService:
    """Preload expensive history and merge it with causal Intra-Finder bars."""

    def __init__(
        self,
        config: PipelineConfig,
        dhan: DhanService,
        market_time: MarketTimeService,
    ) -> None:
        self.config = config
        self.dhan = dhan
        self.market_time = market_time
        self._lock = Lock()

    def prewarm(self, stock: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
        security_id = int(stock["security_id"])
        market_date = self.market_time.market_date_str()
        exchange_segment = str(stock.get("exchange_segment") or "").upper()
        path = self.cache_path(market_date, exchange_segment, security_id)
        if not force:
            cached = self._load_valid_payload(path, security_id, exchange_segment)
            if cached and self._age_seconds(cached.get("fetched_at_ist")) <= 60:
                return cached

        response = self.dhan.fetch_intraday_history(
            security_id,
            days=25,
            interval=1,
            exchange_segment=exchange_segment,
            instrument_candidates=[stock.get("instrument"), "EQUITY"],
        )
        if not response or str(response.get("status") or "").lower() != "success":
            remarks = response.get("remarks") if isinstance(response, dict) else "empty_response"
            raise RuntimeError(f"signal_cache_history_failed::{security_id}::{remarks}")

        payload = {
            "schema_version": 1,
            "market_date": market_date,
            "security_id": security_id,
            "exchange_segment": exchange_segment,
            "instrument": stock.get("instrument") or "EQUITY",
            "fetched_at_ist": self.market_time.now().isoformat(),
            "response": response,
        }
        with self._lock:
            StorageService.save_snapshot(path, payload)
        return payload

    def load_frame(
        self,
        *,
        market_date: str,
        exchange_segment: str,
        security_id: int,
        recent_bars: Optional[Iterable[Dict[str, Any]]] = None,
        max_age_seconds: Optional[float] = None,
    ) -> Optional[pd.DataFrame]:
        segment = str(exchange_segment or "").upper()
        payload = self._load_valid_payload(
            self.cache_path(market_date, segment, int(security_id)),
            int(security_id),
            segment,
        )
        if not payload:
            return None
        maximum_age = float(
            max_age_seconds
            if max_age_seconds is not None
            else self.config.stock_agent_signal_cache_max_age_seconds
        )
        if self._age_seconds(payload.get("fetched_at_ist")) > maximum_age:
            return None

        response = payload.get("response")
        if not isinstance(response, dict):
            return None
        frame = self.dhan.intraday_response_to_df(response)
        return self.merge_recent_bars(frame, recent_bars or [])

    def cache_path(self, market_date: str, exchange_segment: str, security_id: int) -> Path:
        segment = str(exchange_segment or "unknown").lower()
        return self.config.signal_data_cache_dir / market_date / segment / f"{int(security_id)}.json"

    def merge_recent_bars(
        self,
        frame: pd.DataFrame,
        recent_bars: Iterable[Dict[str, Any]],
    ) -> pd.DataFrame:
        records = []
        for bar in recent_bars:
            if not isinstance(bar, dict):
                continue
            timestamp = bar.get("minute_start") or bar.get("timestamp") or bar.get("time_ist")
            if not timestamp:
                continue
            try:
                records.append(
                    {
                        "timestamp": pd.Timestamp(timestamp),
                        "open": float(bar["open"]),
                        "high": float(bar["high"]),
                        "low": float(bar["low"]),
                        "close": float(bar["close"]),
                        "volume": float(bar.get("volume") or 0.0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not records:
            return frame

        recent = pd.DataFrame.from_records(records)
        timestamp = pd.to_datetime(recent["timestamp"], errors="coerce", utc=True)
        # DhanService.intraday_response_to_df returns naive UTC timestamps.
        recent["timestamp"] = timestamp.dt.tz_localize(None)
        combined = pd.concat([frame, recent], ignore_index=True)
        combined["timestamp"] = pd.to_datetime(combined["timestamp"], errors="coerce")
        return (
            combined.dropna(subset=["timestamp"])
            .sort_values("timestamp")
            .drop_duplicates(subset=["timestamp"], keep="last")
            .reset_index(drop=True)
        )

    def _load_valid_payload(
        self,
        path: Path,
        security_id: int,
        exchange_segment: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            payload = StorageService.load_snapshot(path)
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("market_date") != self.market_time.market_date_str():
            return None
        if int(payload.get("security_id") or 0) != int(security_id):
            return None
        if str(payload.get("exchange_segment") or "").upper() != str(exchange_segment).upper():
            return None
        return payload

    def _age_seconds(self, value: Any) -> float:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            now = self.market_time.now()
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=now.tzinfo)
            return max(0.0, (now - parsed.astimezone(now.tzinfo)).total_seconds())
        except (TypeError, ValueError):
            return float("inf")
