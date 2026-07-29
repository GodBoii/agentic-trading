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

    ALLOWED_TIMEFRAMES = {1, 3, 5, 10, 15, 30, 60}

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
        exchange_segment: str = "BSE_EQ",
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
                self.get_live_market_snapshot,
                self.get_ohlc_snapshot,
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

    def get_live_market_snapshot(self) -> str:
        """Get the latest quote, best bid/ask, depth, volume, and session OHLC for the assigned stock."""
        fetched_at = self._now()
        quote: Dict[str, Any] = {}
        ohlc: Dict[str, Any] = {}
        try:
            quote = self.dhan.fetch_quote_batch(
                [self.security_id],
                exchange_segment=self.exchange_segment,
            ).get(self.security_id) or {}
        except Exception:
            pass
        try:
            ohlc = self.dhan.fetch_ohlc_batch(
                [self.security_id],
                exchange_segment=self.exchange_segment,
            ).get(self.security_id) or {}
        except Exception:
            pass
        if not quote and not ohlc:
            return json.dumps(
                {"status": "failure", "remarks": "live_market_snapshot_unavailable"},
                ensure_ascii=True,
            )

        depth = quote.get("depth") if isinstance(quote.get("depth"), dict) else {}
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
        best_bid = self._first_depth_level(depth, "buy")
        best_ask = self._first_depth_level(depth, "sell")
        bid_price = self._first_value(best_bid or {}, "price")
        ask_price = self._first_value(best_ask or {}, "price")
        last_price = self._first_value(quote, "last_price", "lastPrice", "ltp")
        spread_percent = None
        try:
            if float(last_price) > 0 and float(ask_price) >= float(bid_price) > 0:
                spread_percent = ((float(ask_price) - float(bid_price)) / float(last_price)) * 100.0
        except Exception:
            pass
        payload = {
            "security_id": self.security_id,
            "snapshot_fetched_at_ist": fetched_at.isoformat(),
            "last_price": last_price,
            "average_price": quote.get("average_price"),
            "last_trade_time_ist": last_trade_at.isoformat() if last_trade_at is not None else last_trade_time,
            "last_trade_age_seconds": round(last_trade_age, 3) if last_trade_age is not None else None,
            "volume": quote.get("volume"),
            "total_buy_quantity": quote.get("buy_quantity"),
            "total_sell_quantity": quote.get("sell_quantity"),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_percent": round(spread_percent, 4) if spread_percent is not None else None,
            "depth": {
                "buy": (depth.get("buy") or [])[:5],
                "sell": (depth.get("sell") or [])[:5],
            },
            "session_ohlc": quote.get("ohlc") or ohlc.get("ohlc"),
            "upper_circuit": quote.get("upper_circuit_limit"),
            "lower_circuit": quote.get("lower_circuit_limit"),
        }
        return json.dumps(self._without_empty(payload), ensure_ascii=True)

    def get_current_stock_state(self) -> str:
        """Fetch a new quote and new recent candles for the final pre-decision check.

        Call this after the main analysis, immediately before placing an order
        or giving the final no-trade conclusion.
        """
        fetched_at = self._now()
        payload: Dict[str, Any] = {
            "security_id": self.security_id,
            "snapshot_fetched_at_ist": fetched_at.isoformat(),
        }
        try:
            quote_payload = json.loads(self.get_live_market_snapshot())
            if isinstance(quote_payload, dict) and quote_payload.get("status") != "failure":
                payload["live_market"] = quote_payload
        except Exception:
            pass
        try:
            frame = self._load_intraday_frame(force_refresh=True)
            current = frame.loc[frame["timestamp"].dt.date == fetched_at.date()].copy()
            if not current.empty:
                payload["candle_data_as_of_ist"] = current["timestamp"].iloc[-1].isoformat()
                payload["recent_1m_candles"] = self._frame_records(current, 1, 8)
                payload["recent_5m_candles"] = self._frame_records(current, 5, 4)
        except Exception:
            pass
        if len(payload) == 2:
            payload.update({"status": "failure", "remarks": "current_stock_state_unavailable"})
        else:
            payload["status"] = "success"
        return json.dumps(payload, ensure_ascii=True)

    def get_ohlc_snapshot(
        self,
        timeframe_minutes: int = 5,
        candle_count: int = 40,
    ) -> str:
        """Get exact recent OHLCV candles when the attached charts are not sufficient.

        Args:
            timeframe_minutes: Candle interval. Supported values are 1, 3, 5, 10, 15, 30, and 60.
            candle_count: Number of current-session candles to return, from 5 to 60.
        """
        timeframe = int(timeframe_minutes)
        if timeframe not in self.ALLOWED_TIMEFRAMES:
            return json.dumps(
                {
                    "status": "failure",
                    "remarks": "unsupported_timeframe",
                    "supported_timeframes": sorted(self.ALLOWED_TIMEFRAMES),
                },
                ensure_ascii=True,
            )
        limit = min(60, max(5, int(candle_count)))
        try:
            frame = self._load_intraday_frame()
        except Exception as exc:
            return json.dumps(
                {"status": "failure", "remarks": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=True,
            )
        if frame.empty:
            return json.dumps({"status": "failure", "remarks": "no_intraday_candles"}, ensure_ascii=True)

        current_market_date = self.market_time.now().date()
        current_frame = frame.loc[frame["timestamp"].dt.date == current_market_date].copy()
        if current_frame.empty:
            return json.dumps(
                {"status": "failure", "remarks": "no_current_session_candles"},
                ensure_ascii=True,
            )
        records = self._frame_records(current_frame, timeframe, limit)
        return json.dumps(
            {
                "security_id": self.security_id,
                "snapshot_fetched_at_ist": self._now().isoformat(),
                "candle_data_as_of_ist": current_frame["timestamp"].iloc[-1].isoformat(),
                "timeframe_minutes": timeframe,
                "candles": records,
            },
            ensure_ascii=True,
        )

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
            days=5,
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

    @staticmethod
    def _first_depth_level(depth: Dict[str, Any], side: str) -> Any:
        levels = depth.get(side)
        return levels[0] if isinstance(levels, list) and levels else None

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
