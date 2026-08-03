from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
from agno.tools import Toolkit

from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService


class StockMarketDataToolkit(Toolkit):
    """Live and historical market data scoped to one assigned stock."""

    def __init__(
        self,
        dhan: DhanService,
        market_time: MarketTimeService,
        security_id: int,
        symbol: str,
        display_name: str,
        stock_context: Optional[Dict[str, Any]] = None,
        instrument: Optional[str] = None,
        intraday_frame: Optional[pd.DataFrame] = None,
        intraday_frame_fetched_at: Optional[datetime] = None,
        exchange_segment: Optional[str] = "BSE_EQ",
        history_cache_max_age_seconds: float = 20.0,
    ) -> None:
        self.dhan = dhan
        self.market_time = market_time
        self.security_id = int(security_id)
        self.symbol = str(symbol or "")
        self.display_name = str(display_name or self.symbol)
        self.stock_context = stock_context if isinstance(stock_context, dict) else {}
        self.instrument = str(instrument or "EQUITY")
        self.exchange_segment = str(exchange_segment or "BSE_EQ").upper()
        if self.exchange_segment not in {"NSE_EQ", "BSE_EQ"}:
            raise ValueError("StockMarketDataToolkit requires NSE_EQ or BSE_EQ.")
        self._intraday_frame = self._prepare_frame(intraday_frame)
        self._intraday_frame_fetched_at = (
            intraday_frame_fetched_at
            if intraday_frame_fetched_at is not None
            else (self._now() if intraday_frame is not None else None)
        )
        self.history_cache_max_age_seconds = max(0.0, float(history_cache_max_age_seconds))
        super().__init__(
            name="stock_market_data_tools",
            tools=[
                self.get_security_overview,
                self.get_market_time,
                self.get_current_stock_state,
            ],
        )

    def get_security_overview(self) -> str:
        """Get identity, historical liquidity measures, and tradability data for the assigned stock."""
        stock = self.stock_context.get("stock") or {}
        tradability = dict(stock.get("static_tradability") or {})
        tick_size = tradability.pop("tick_size", None)
        if tick_size not in (None, ""):
            try:
                raw_tick = float(tick_size)
                tradability["tick_size_rupees"] = raw_tick / 100.0 if raw_tick >= 1 else raw_tick
            except Exception:
                pass

        stage2 = self.stock_context.get("stage2") or {}
        payload = {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "display_name": self.display_name,
            "exchange_segment": self.exchange_segment,
            "average_daily_value_crore": stock.get("adv_20_cr"),
            "historical_atr_percent": stock.get("atr_percent"),
            "average_volume_20_sessions": stock.get("avg_volume_20"),
            "stage2_momentum_snapshot": {
                "score": stage2.get("score"),
                "selection_score": stage2.get("selection_score"),
                "time_of_day_rvol": stage2.get("time_of_day_rvol"),
                "price_vs_vwap_percent": stage2.get("price_vs_vwap_percent"),
                "opening_range_breakout_percent": stage2.get("opening_range_breakout_percent"),
                "volume_acceleration_ratio": stage2.get("volume_acceleration_ratio"),
                "selection_reason": stage2.get("stage2_reason"),
                "live_liquidity": stage2.get("live_liquidity"),
                "data_quality": stage2.get("data_quality"),
            },
            "tradability": tradability,
        }
        return json.dumps(self._without_empty(payload), ensure_ascii=True)

    def get_market_time(self) -> str:
        """Get the current Indian market time and regular-session status."""
        now = self.market_time.now()
        open_at = now.replace(
            hour=self.market_time.config.market_open_hour,
            minute=self.market_time.config.market_open_minute,
            second=0,
            microsecond=0,
        )
        close_at = now.replace(
            hour=self.market_time.config.market_close_hour,
            minute=self.market_time.config.market_close_minute,
            second=0,
            microsecond=0,
        )
        payload = {
            "date": now.strftime("%d %B %Y"),
            "time_ist": now.strftime("%H:%M:%S IST"),
            "regular_session": "09:15-15:30 IST",
            "is_open_now": bool(open_at <= now <= close_at),
            "minutes_to_close": max(0, int((close_at - now).total_seconds() // 60)),
        }
        return json.dumps(payload, ensure_ascii=True)

    def _fetch_live_market_snapshot(self) -> tuple[Dict[str, Any], list[str]]:
        """Fetch a compact live snapshot without exposing depth to the model."""
        fetched_at = self._now()
        quote: Dict[str, Any] = {}
        ohlc: Dict[str, Any] = {}
        errors: list[str] = []
        try:
            quote = self.dhan.fetch_quote_batch(
                [self.security_id],
                exchange_segment=self.exchange_segment,
            ).get(self.security_id) or {}
        except Exception as exc:
            errors.append(f"quote:{type(exc).__name__}:{exc}")
        if not isinstance(quote.get("ohlc"), dict) or not quote.get("ohlc"):
            try:
                ohlc = self.dhan.fetch_ohlc_batch(
                    [self.security_id],
                    exchange_segment=self.exchange_segment,
                ).get(self.security_id) or {}
            except Exception as exc:
                errors.append(f"ohlc:{type(exc).__name__}:{exc}")

        last_trade_time = self._first_value(
            quote,
            "last_trade_time",
            "last_traded_time",
            "lastTradeTime",
        )
        last_trade_at = self._parse_market_timestamp(last_trade_time)
        last_trade_age = (
            max(0.0, (fetched_at - last_trade_at).total_seconds())
            if last_trade_at is not None
            else None
        )
        session_ohlc = quote.get("ohlc") or ohlc.get("ohlc") or {}
        payload = {
            "as_of_ist": fetched_at.isoformat(),
            "last_price": self._first_value(quote, "last_price", "lastPrice", "ltp"),
            "average_price": quote.get("average_price"),
            "last_trade_time_ist": last_trade_at.isoformat() if last_trade_at is not None else last_trade_time,
            "last_trade_age_seconds": round(last_trade_age, 3) if last_trade_age is not None else None,
            "cumulative_volume": quote.get("volume"),
            "session_ohlc": session_ohlc,
            "upper_circuit": quote.get("upper_circuit_limit"),
            "lower_circuit": quote.get("lower_circuit_limit"),
        }
        return self._without_empty(payload), errors

    def get_current_stock_state(self) -> str:
        """Fetch a new quote and new recent candles for the final pre-decision check.

        Call this after the main analysis, immediately before placing an order
        or giving the final no-trade conclusion.
        """
        fetched_at = self._now()
        payload: Dict[str, Any] = {
            "source": "dhan_quote_and_intraday",
            "security_id": self.security_id,
            "as_of_ist": fetched_at.isoformat(),
        }
        missing_fields: list[str] = []
        errors: list[str] = []

        live_market, live_errors = self._fetch_live_market_snapshot()
        errors.extend(live_errors)
        if live_market:
            payload["quote"] = live_market
        else:
            missing_fields.append("quote")

        try:
            frame = self._load_intraday_frame(force_refresh=True)
            current = frame.loc[frame["timestamp"].dt.date == fetched_at.date()].copy()
            if not current.empty:
                candle_as_of = current["timestamp"].iloc[-1]
                payload["candle_data_as_of_ist"] = candle_as_of.isoformat()
                payload["candle_data_age_seconds"] = round(
                    max(0.0, (fetched_at - candle_as_of.to_pydatetime()).total_seconds()),
                    3,
                )
                payload["one_minute"] = self._latest_candle_pair(current, 1, fetched_at)
                payload["five_minute"] = self._latest_candle_pair(current, 5, fetched_at)
            else:
                missing_fields.extend(["one_minute", "five_minute"])
        except Exception as exc:
            missing_fields.extend(["one_minute", "five_minute"])
            errors.append(f"intraday:{type(exc).__name__}:{exc}")

        if "quote" not in payload and "one_minute" not in payload:
            payload["status"] = "error"
            payload["remarks"] = "current_stock_state_unavailable"
        elif missing_fields or errors:
            payload["status"] = "partial"
        else:
            payload["status"] = "success"
        if missing_fields:
            payload["missing_fields"] = sorted(set(missing_fields))
        if errors:
            payload["errors"] = errors
        return json.dumps(self._without_empty(payload), ensure_ascii=True)

    def _latest_candle_pair(
        self,
        frame: pd.DataFrame,
        timeframe: int,
        now: datetime,
    ) -> Dict[str, Any]:
        records = self._frame_records(frame, timeframe, max(3, timeframe + 1))
        if not records:
            return {}
        result: Dict[str, Any] = {}
        latest = records[-1]
        latest_start = datetime.fromisoformat(str(latest["time_ist"]))
        latest_complete = now >= latest_start + pd.Timedelta(minutes=timeframe)
        if latest_complete:
            result["latest_completed"] = latest
        else:
            result["current_partial"] = latest
            if len(records) >= 2:
                result["latest_completed"] = records[-2]
        return result

    def _load_intraday_frame(self, force_refresh: bool = False) -> pd.DataFrame:
        cache_age = self._cache_age_seconds()
        if (
            not force_refresh
            and self._intraday_frame is not None
            and cache_age is not None
            and cache_age <= self.history_cache_max_age_seconds
        ):
            return self._intraday_frame
        response = self.dhan.fetch_intraday_history(
            self.security_id,
            days=2 if force_refresh else 25,
            interval=1,
            exchange_segment=self.exchange_segment,
            instrument_candidates=[self.instrument, "EQUITY"],
        )
        if not response or str(response.get("status") or "").lower() != "success":
            remarks = response.get("remarks") if isinstance(response, dict) else "empty_response"
            raise RuntimeError(str(remarks))
        self._intraday_frame = self._prepare_frame(self.dhan.intraday_response_to_df(response))
        self._intraday_frame_fetched_at = self._now()
        return self._intraday_frame if self._intraday_frame is not None else pd.DataFrame()

    def _frame_records(
        self,
        frame: pd.DataFrame,
        timeframe: int,
        limit: int,
    ) -> list[Dict[str, Any]]:
        local = frame.set_index("timestamp")
        if timeframe > 1:
            local = (
                local[["open", "high", "low", "close", "volume"]]
                .resample(f"{timeframe}min", label="left", closed="left")
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )
                .dropna(subset=["open", "high", "low", "close"])
            )
        records = []
        for timestamp, row in local.tail(limit).iterrows():
            records.append(
                {
                    "time_ist": timestamp.isoformat(),
                    "open": round(float(row["open"]), 4),
                    "high": round(float(row["high"]), 4),
                    "low": round(float(row["low"]), 4),
                    "close": round(float(row["close"]), 4),
                    "volume": int(float(row.get("volume") or 0)),
                }
            )
        return records

    def _cache_age_seconds(self) -> Optional[float]:
        if self._intraday_frame_fetched_at is None:
            return None
        try:
            return max(0.0, (self._now() - self._intraday_frame_fetched_at).total_seconds())
        except Exception:
            return None

    def _now(self) -> datetime:
        return self.market_time.now()

    def _parse_market_timestamp(self, value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        text = str(value).strip()
        for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=self.market_time.tz)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=self.market_time.tz)
            return parsed.astimezone(self.market_time.tz)
        except ValueError:
            return None

    def _prepare_frame(self, frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if frame is None:
            return None
        prepared = frame.copy()
        if prepared.empty:
            return prepared
        timestamp = pd.to_datetime(prepared["timestamp"], errors="coerce")
        if timestamp.dt.tz is None:
            timestamp = timestamp.dt.tz_localize("UTC")
        prepared["timestamp"] = timestamp.dt.tz_convert(self.market_time.tz)
        return prepared.dropna(subset=["timestamp"]).sort_values("timestamp")

    @staticmethod
    def _first_value(data: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if data.get(key) not in (None, ""):
                return data.get(key)
        return None

    @classmethod
    def _without_empty(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                cleaned = cls._without_empty(item)
                if cleaned not in (None, "", [], {}):
                    result[key] = cleaned
            return result
        if isinstance(value, list):
            return [cls._without_empty(item) for item in value if item not in (None, "", [], {})]
        return value
