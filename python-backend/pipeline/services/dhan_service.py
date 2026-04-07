import math
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Condition
from typing import Any, DefaultDict, Dict, List, Optional

import pandas as pd
from dhanhq import DhanContext, HistoricalData, MarketFeed, dhanhq
from dotenv import dotenv_values

from pipeline.config import PipelineConfig


class DhanService:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.request_times = deque()
        self.rate_condition = Condition()
        self.quote_request_gap = 1.1

        root_env = dotenv_values(config.root_dir / ".env")
        backend_env = dotenv_values(config.backend_dir / ".env")
        merged: Dict[str, str] = {}
        merged.update({k: v for k, v in root_env.items() if v is not None})
        merged.update({k: v for k, v in backend_env.items() if v is not None})

        client_id = merged.get("DHAN_DATA_CLIENT_ID") or merged.get("DHAN_CLIENT_ID")
        access_token = merged.get("DHAN_DATA_ACCESS_TOKEN") or merged.get("DHAN_ACCESS_TOKEN")
        if not client_id or not access_token:
            raise ValueError("Missing Dhan credentials. Expected DHAN_DATA_CLIENT_ID and DHAN_DATA_ACCESS_TOKEN.")

        self.dhan_context = DhanContext(client_id, access_token)
        self.market_api = dhanhq(self.dhan_context)
        self.historical_api = HistoricalData(self.dhan_context)

    def acquire_data_slot(self) -> None:
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

    def fetch_daily_history(self, security_id: int, days: int = 30, retries: int = 3) -> Optional[Dict[str, Any]]:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        last_response = None

        for attempt in range(retries):
            self.acquire_data_slot()
            resp = self.historical_api.historical_daily_data(
                security_id=str(security_id),
                exchange_segment="BSE_EQ",
                instrument_type="EQUITY",
                from_date=start_date.isoformat(),
                to_date=end_date.isoformat(),
            )
            last_response = resp

            if str(resp.get("status", "")).lower() == "success":
                return resp

            if self._is_rate_limited(resp):
                time.sleep(min(2.0, 0.4 * (attempt + 1)))
                continue
            return resp

        return last_response

    def fetch_intraday_history(self, security_id: int, days: int = 5, interval: int = 1, retries: int = 3) -> Optional[Dict[str, Any]]:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        last_response = None

        for attempt in range(retries):
            self.acquire_data_slot()
            resp = self.historical_api.intraday_minute_data(
                security_id=str(security_id),
                exchange_segment="BSE_EQ",
                instrument_type="EQUITY",
                from_date=start_date.isoformat(),
                to_date=end_date.isoformat(),
                interval=interval,
            )
            last_response = resp

            if str(resp.get("status", "")).lower() == "success":
                return resp

            if self._is_rate_limited(resp):
                time.sleep(min(2.0, 0.4 * (attempt + 1)))
                continue
            return resp

        return last_response

    def fetch_quote_batch(self, security_ids: List[int]) -> Dict[int, Dict[str, Any]]:
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
        return "too many requests" in remarks or "too many requests" in data_blob or "805" in remarks or "805" in data_blob
