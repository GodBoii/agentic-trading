import json
import math
import random
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Condition
from typing import Any, DefaultDict, Dict, List, Optional

import pandas as pd
import requests
from dhanhq import DhanContext, HistoricalData, MarketFeed, dhanhq
from dotenv import dotenv_values

from pipeline.config import PipelineConfig

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - non-posix fallback
    fcntl = None


class DhanService:
    VALID_HISTORICAL_INSTRUMENTS = {
        "INDEX",
        "FUTIDX",
        "OPTIDX",
        "EQUITY",
        "FUTSTK",
        "OPTSTK",
        "FUTCOM",
        "OPTFUT",
        "FUTCUR",
        "OPTCUR",
    }

    def __init__(self, config: PipelineConfig, prefer_gateway: bool = True):
        self.config = config
        self.request_times = deque()
        self.rate_limit_hits = deque()
        self.rate_condition = Condition()
        self.quote_request_gap = 1.1
        self.prefer_gateway = prefer_gateway

        root_env = dotenv_values(config.root_dir / ".env")
        backend_env = dotenv_values(config.backend_dir / ".env")
        merged: Dict[str, str] = {}
        merged.update({k: v for k, v in root_env.items() if v is not None})
        merged.update({k: v for k, v in backend_env.items() if v is not None})

        self.client_id = merged.get("DHAN_DATA_CLIENT_ID") or merged.get("DHAN_CLIENT_ID")
        self.access_token = merged.get("DHAN_DATA_ACCESS_TOKEN") or merged.get("DHAN_ACCESS_TOKEN")
        self.app_id = merged.get("DHAN_APP_ID")
        self.app_secret = merged.get("DHAN_APP_SECRET")

        if not self.client_id or not self.access_token:
            raise ValueError("Missing Dhan credentials. Expected DHAN_DATA_CLIENT_ID and DHAN_DATA_ACCESS_TOKEN.")

        self.dhan_context = DhanContext(self.client_id, self.access_token)
        self.market_api = dhanhq(self.dhan_context)
        self.historical_api = HistoricalData(self.dhan_context)
        self.login_api = self.dhan_context.get_dhan_login()
        self.gateway_url = (
            self.config.market_data_gateway_url()
            if self.prefer_gateway
            else None
        )
        self.gateway_timeout_seconds = self.config.market_data_gateway_timeout_seconds
        self.gateway_session = requests.Session() if self.gateway_url else None

    def _normalize_historical_instruments(self, instrument_candidates: Optional[List[str]]) -> List[str]:
        # Dhan historical API accepts Dhan instrument names (e.g. EQUITY), not exchange-type tags like ES.
        normalized: List[str] = []
        for raw in instrument_candidates or []:
            if not raw:
                continue
            candidate = str(raw).strip().upper()
            if candidate == "ES":
                candidate = "EQUITY"
            if candidate in self.VALID_HISTORICAL_INSTRUMENTS:
                normalized.append(candidate)

        if "EQUITY" not in normalized:
            normalized.append("EQUITY")

        # preserve order while deduplicating
        return list(dict.fromkeys(normalized))

    def credentials_summary(self) -> Dict[str, Any]:
        masked_client = (
            f"{self.client_id[:2]}***{self.client_id[-2:]}"
            if self.client_id and len(self.client_id) >= 4
            else "***"
        )
        return {
            "client_id_masked": masked_client,
            "has_data_client_id": bool(self.client_id),
            "has_data_access_token": bool(self.access_token),
            "has_app_id": bool(self.app_id),
            "has_app_secret": bool(self.app_secret),
        }

    def fetch_user_profile(self) -> Dict[str, Any]:
        if self.gateway_url:
            response = self._gateway_post("/v1/user-profile", {})
            return response if isinstance(response, dict) else {"status": "failure", "remarks": "invalid_gateway_response"}
        try:
            response = self.login_api.user_profile(self.access_token)
            return {"status": "success", "data": response}
        except Exception as exc:
            return {"status": "failure", "remarks": str(exc), "data": None}

    def _gateway_post(self, path: str, payload: Dict[str, Any]) -> Any:
        if not self.gateway_url or not self.gateway_session:
            raise RuntimeError("Market data gateway is not configured.")

        response = self.gateway_session.post(
            f"{self.gateway_url}{path}",
            json=payload,
            timeout=self.gateway_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", False):
            raise RuntimeError(str(body.get("error", "gateway_error")))
        return body.get("data")

    def _prune_rate_limit_hits(self, now: Optional[float] = None) -> None:
        now = now or time.time()
        window = self.config.rate_limit_cooldown_window_seconds
        while self.rate_limit_hits and now - self.rate_limit_hits[0] > window:
            self.rate_limit_hits.popleft()

    def _compute_rate_limit_delay(self, attempt: int) -> float:
        base_delay = min(
            self.config.rate_limit_backoff_max_seconds,
            self.config.rate_limit_backoff_base_seconds * (2 ** attempt),
        )
        jitter = random.uniform(0.0, self.config.rate_limit_backoff_jitter_seconds)
        now = time.time()
        self.rate_limit_hits.append(now)
        self._prune_rate_limit_hits(now)

        cooldown = 0.0
        if len(self.rate_limit_hits) >= self.config.rate_limit_cooldown_trigger:
            cooldown = self.config.rate_limit_cooldown_seconds + random.uniform(
                0.0,
                self.config.rate_limit_backoff_jitter_seconds,
            )
            self.rate_limit_hits.clear()

        return base_delay + jitter + cooldown

    def acquire_data_slot(self) -> None:
        self._acquire_shared_data_slot()
        self._acquire_local_data_slot()

    def _acquire_local_data_slot(self) -> None:
        with self.rate_condition:
            while True:
                now = time.time()
                while self.request_times and now - self.request_times[0] >= 1.0:
                    self.request_times.popleft()
                if len(self.request_times) < self.config.historical_rate_limit_per_sec:
                    self.request_times.append(now)
                    self.rate_condition.notify_all()
                    return
                wait_time = max(0.01, 1.0 - (now - self.request_times[0]))
                self.rate_condition.wait(timeout=wait_time)

    def _acquire_shared_data_slot(self) -> None:
        if fcntl is None:
            return

        state_path = self.config.dhan_rate_limit_state_path
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if not state_path.exists():
            state_path.write_text('{"request_times": []}', encoding="utf-8")

        window_seconds = self.config.shared_rate_limit_window_seconds
        poll_seconds = self.config.shared_rate_limit_poll_seconds

        while True:
            with state_path.open("r+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    raw = handle.read().strip()
                    payload = json.loads(raw) if raw else {"request_times": []}
                except json.JSONDecodeError:
                    payload = {"request_times": []}

                now = time.time()
                request_times = [
                    float(item)
                    for item in payload.get("request_times", [])
                    if now - float(item) < window_seconds
                ]

                if len(request_times) < self.config.historical_rate_limit_per_sec:
                    request_times.append(now)
                    handle.seek(0)
                    handle.truncate()
                    json.dump({"request_times": request_times}, handle)
                    handle.flush()
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    return

                oldest = request_times[0]
                wait_time = max(poll_seconds, window_seconds - (now - oldest))
                handle.seek(0)
                handle.truncate()
                json.dump({"request_times": request_times}, handle)
                handle.flush()
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

            time.sleep(wait_time)

    def fetch_daily_history(
        self,
        security_id: int,
        days: int = 30,
        retries: int = 3,
        exchange_segment: str = "BSE_EQ",
        instrument_candidates: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.gateway_url:
            return self._gateway_post(
                "/v1/daily-history",
                {
                    "security_id": security_id,
                    "days": days,
                    "retries": retries,
                    "exchange_segment": exchange_segment,
                    "instrument_candidates": instrument_candidates,
                },
            )

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        last_response = None
        candidates = self._normalize_historical_instruments(instrument_candidates or ["EQUITY"])

        for instrument_name in candidates:
            for attempt in range(retries):
                self.acquire_data_slot()
                resp = self.historical_api.historical_daily_data(
                    security_id=str(security_id),
                    exchange_segment=exchange_segment,
                    instrument_type=instrument_name,
                    from_date=start_date.isoformat(),
                    to_date=end_date.isoformat(),
                )
                if isinstance(resp, dict):
                    resp.setdefault("_debug", {})
                    resp["_debug"]["instrument_used"] = instrument_name
                    resp["_debug"]["exchange_segment_used"] = exchange_segment
                last_response = resp

                if str(resp.get("status", "")).lower() == "success":
                    return resp

                if self._is_rate_limited(resp):
                    time.sleep(self._compute_rate_limit_delay(attempt))
                    continue
                break

        return last_response

    def fetch_intraday_history(
        self,
        security_id: int,
        days: int = 5,
        interval: int = 1,
        retries: int = 3,
        exchange_segment: str = "BSE_EQ",
        instrument_candidates: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.gateway_url:
            return self._gateway_post(
                "/v1/intraday-history",
                {
                    "security_id": security_id,
                    "days": days,
                    "interval": interval,
                    "retries": retries,
                    "exchange_segment": exchange_segment,
                    "instrument_candidates": instrument_candidates,
                },
            )

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        last_response = None
        candidates = self._normalize_historical_instruments(instrument_candidates or ["EQUITY"])

        for instrument_name in candidates:
            for attempt in range(retries):
                self.acquire_data_slot()
                resp = self.historical_api.intraday_minute_data(
                    security_id=str(security_id),
                    exchange_segment=exchange_segment,
                    instrument_type=instrument_name,
                    from_date=start_date.isoformat(),
                    to_date=end_date.isoformat(),
                    interval=interval,
                )
                if isinstance(resp, dict):
                    resp.setdefault("_debug", {})
                    resp["_debug"]["instrument_used"] = instrument_name
                    resp["_debug"]["exchange_segment_used"] = exchange_segment
                last_response = resp

                if str(resp.get("status", "")).lower() == "success":
                    return resp

                if self._is_rate_limited(resp):
                    time.sleep(self._compute_rate_limit_delay(attempt))
                    continue
                break

        return last_response

    def fetch_quote_batch(self, security_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if self.gateway_url:
            response = self._gateway_post("/v1/quote-batch", {"security_ids": security_ids})
            return {
                int(raw_security_id): value
                for raw_security_id, value in (response or {}).items()
            }

        self.acquire_data_slot()
        time.sleep(self.quote_request_gap)
        resp = self.market_api.quote_data({"BSE_EQ": security_ids})
        if str(resp.get("status", "")).lower() != "success":
            return {}

        data = resp.get("data", {}).get("data", {}).get("BSE_EQ", {})
        parsed: Dict[int, Dict[str, Any]] = {}
        for raw_security_id, value in data.items():
            try:
                parsed[int(raw_security_id)] = value
            except Exception:
                continue
        return parsed

    def fetch_ohlc_batch(self, security_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if self.gateway_url:
            response = self._gateway_post("/v1/ohlc-batch", {"security_ids": security_ids})
            return {
                int(raw_security_id): value
                for raw_security_id, value in (response or {}).items()
            }

        self.acquire_data_slot()
        time.sleep(self.quote_request_gap)
        resp = self.market_api.ohlc_data({"BSE_EQ": security_ids})
        if str(resp.get("status", "")).lower() != "success":
            return {}

        data = resp.get("data", {}).get("data", {}).get("BSE_EQ", {})
        parsed: Dict[int, Dict[str, Any]] = {}
        for raw_security_id, value in data.items():
            try:
                parsed[int(raw_security_id)] = value
            except Exception:
                continue
        return parsed

    def build_marketfeed(self, instruments: List[tuple]) -> MarketFeed:
        return MarketFeed(self.dhan_context, instruments, version="v2")

    def daily_response_to_df(self, resp: Dict[str, Any]) -> pd.DataFrame:
        data = resp.get("data", {})
        frame = pd.DataFrame(
            {
                "timestamp": data.get("timestamp", []),
                "open": data.get("open", []),
                "high": data.get("high", []),
                "low": data.get("low", []),
                "close": data.get("close", []),
                "volume": data.get("volume", []),
            }
        )
        if not frame.empty:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", errors="coerce")
            frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
        return frame

    def intraday_response_to_df(self, resp: Dict[str, Any]) -> pd.DataFrame:
        return self.daily_response_to_df(resp)

    def compute_atr_percent(self, frame: pd.DataFrame, period: int = 14) -> float:
        tr1 = frame["high"] - frame["low"]
        tr2 = (frame["high"] - frame["close"].shift()).abs()
        tr3 = (frame["low"] - frame["close"].shift()).abs()
        atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(window=period).mean()
        latest_close = float(frame["close"].iloc[-1]) if not frame.empty else 0.0
        latest_atr = float(atr.iloc[-1]) if len(atr) > 0 and pd.notna(atr.iloc[-1]) else 0.0
        return (latest_atr / latest_close) * 100 if latest_close > 0 else 0.0

    def compute_time_of_day_rvol(self, frame: pd.DataFrame) -> Optional[float]:
        if frame.empty or "volume" not in frame.columns:
            return None

        frame = frame.copy()
        frame["date"] = frame["timestamp"].dt.date
        frame["time"] = frame["timestamp"].dt.time
        today = frame["date"].max()
        today_frame = frame[frame["date"] == today].sort_values("timestamp")
        if today_frame.empty:
            return None

        current_cutoff = today_frame["timestamp"].max().time()
        grouped: DefaultDict[Any, pd.DataFrame] = defaultdict(pd.DataFrame)
        for trading_date, date_frame in frame.groupby("date"):
            grouped[trading_date] = date_frame.sort_values("timestamp")

        today_cum_volume = float(today_frame["volume"].sum())
        baselines: List[float] = []
        for trading_date, date_frame in grouped.items():
            if trading_date == today:
                continue
            comparable = date_frame[date_frame["timestamp"].dt.time <= current_cutoff]
            if not comparable.empty:
                baselines.append(float(comparable["volume"].sum()))

        if not baselines:
            return None

        baseline_avg = sum(baselines) / len(baselines)
        if math.isclose(baseline_avg, 0.0):
            return None
        return today_cum_volume / baseline_avg

    def _is_rate_limited(self, resp: Dict[str, Any]) -> bool:
        remarks = str(resp.get("remarks", "")).lower()
        data_blob = str(resp.get("data", "")).lower()
        return (
            "too many requests" in remarks
            or "too many requests" in data_blob
            or "dh-904" in remarks
            or "dh-904" in data_blob
            or "904" in remarks
            or "904" in data_blob
            or "805" in remarks
            or "805" in data_blob
        )
