from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

import requests

from pipeline.config import PipelineConfig
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


@dataclass(frozen=True)
class MarketSessionStatus:
    market_date: str
    is_trading_day: bool
    is_market_hours: bool
    is_before_open: bool
    is_after_close: bool
    is_new_entry_window: bool
    reason: str
    source: str
    open_at_ist: str
    close_at_ist: str
    new_entry_cutoff_ist: str
    protect_positions_at_ist: str
    calendar_checked_at_ist: str
    external_status: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_date": self.market_date,
            "is_trading_day": self.is_trading_day,
            "is_market_hours": self.is_market_hours,
            "is_before_open": self.is_before_open,
            "is_after_close": self.is_after_close,
            "is_new_entry_window": self.is_new_entry_window,
            "reason": self.reason,
            "source": self.source,
            "open_at_ist": self.open_at_ist,
            "close_at_ist": self.close_at_ist,
            "new_entry_cutoff_ist": self.new_entry_cutoff_ist,
            "protect_positions_at_ist": self.protect_positions_at_ist,
            "calendar_checked_at_ist": self.calendar_checked_at_ist,
            "external_status": self.external_status,
        }


class MarketCalendarService:
    """Market-day calendar with local fallback and optional NSE holiday sync.

    The runtime must never depend on the frontend being online. This service
    gives backend processes a single place to answer: is today a tradable day,
    what session window are we in, and should new entries still be allowed?
    """

    NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
    NSE_HOME_URL = "https://www.nseindia.com"

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.market_time = MarketTimeService(config)
        self.sync_enabled = self._env_bool("MARKET_CALENDAR_NSE_SYNC_ENABLED", True)
        self.sync_timeout_seconds = float(os.getenv("MARKET_CALENDAR_NSE_TIMEOUT_SECONDS", "8"))
        self.cache_ttl_seconds = int(os.getenv("MARKET_CALENDAR_CACHE_TTL_SECONDS", str(12 * 60 * 60)))

    def session_status(self) -> MarketSessionStatus:
        now = self.market_time.now()
        market_date = now.date().isoformat()
        open_dt = self._datetime_for_time(self._time_from_hhmm(self._open_time()))
        close_dt = self._datetime_for_time(self._time_from_hhmm(self._close_time()))
        new_entry_cutoff_dt = self._datetime_for_time(self._time_from_hhmm(self.config.new_entry_cutoff_time))
        protect_dt = self._datetime_for_time(self._time_from_hhmm(self.config.protect_positions_time))

        trading_day_info = self.is_trading_day(now.date())
        is_market_hours = trading_day_info["is_trading_day"] and open_dt <= now <= close_dt
        is_new_entry_window = trading_day_info["is_trading_day"] and open_dt <= now <= new_entry_cutoff_dt

        if not trading_day_info["is_trading_day"]:
            reason = trading_day_info["reason"]
        elif now < open_dt:
            reason = "before_market_open"
        elif now > close_dt:
            reason = "after_market_close"
        elif now > new_entry_cutoff_dt:
            reason = "market_open_new_entries_closed"
        else:
            reason = "market_open_new_entries_allowed"

        return MarketSessionStatus(
            market_date=market_date,
            is_trading_day=bool(trading_day_info["is_trading_day"]),
            is_market_hours=bool(is_market_hours),
            is_before_open=now < open_dt,
            is_after_close=now > close_dt,
            is_new_entry_window=bool(is_new_entry_window),
            reason=reason,
            source=str(trading_day_info["source"]),
            open_at_ist=open_dt.isoformat(),
            close_at_ist=close_dt.isoformat(),
            new_entry_cutoff_ist=new_entry_cutoff_dt.isoformat(),
            protect_positions_at_ist=protect_dt.isoformat(),
            calendar_checked_at_ist=now.isoformat(),
            external_status=trading_day_info.get("external_status"),
        )

    def is_trading_day(self, candidate: date) -> Dict[str, Any]:
        forced = self._forced_status()
        if forced is not None:
            return forced

        if candidate.weekday() >= 5:
            return {"is_trading_day": False, "reason": "weekend", "source": "local_weekday"}

        manual_holidays = self._manual_holidays()
        if candidate.isoformat() in manual_holidays:
            return {
                "is_trading_day": False,
                "reason": "manual_holiday_override",
                "source": str(self.config.market_holidays_path.name),
            }

        cache = self._load_or_refresh_nse_cache()
        holidays = self._holiday_dates_from_cache(cache)
        if candidate.isoformat() in holidays:
            return {
                "is_trading_day": False,
                "reason": "nse_trading_holiday",
                "source": "nse_holiday_cache",
                "external_status": self._cache_metadata(cache),
            }

        source = "nse_holiday_cache" if holidays else "local_weekday_fallback"
        return {
            "is_trading_day": True,
            "reason": "trading_day",
            "source": source,
            "external_status": self._cache_metadata(cache),
        }

    def refresh_nse_holidays(self, force: bool = False) -> Dict[str, Any]:
        existing = StorageService.load_snapshot(self.config.market_calendar_cache_path)
        if not force and existing and not self._cache_is_stale(existing):
            return existing

        if not self.sync_enabled:
            return existing or self._empty_cache("nse_sync_disabled")

        try:
            session = requests.Session()
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Referer": self.NSE_HOME_URL,
            }
            session.get(self.NSE_HOME_URL, headers=headers, timeout=self.sync_timeout_seconds)
            response = session.get(self.NSE_HOLIDAY_URL, headers=headers, timeout=self.sync_timeout_seconds)
            response.raise_for_status()
            raw_payload = response.json()
            cache = {
                "stage": "market_calendar_cache",
                "source": "nse_holiday_master",
                "source_url": self.NSE_HOLIDAY_URL,
                "generated_at_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "status": "success",
                "holiday_dates": sorted(self._extract_dates(raw_payload)),
                "raw_group_count": self._count_holiday_groups(raw_payload),
            }
            StorageService.save_snapshot(self.config.market_calendar_cache_path, cache)
            return cache
        except Exception as exc:
            fallback = existing or self._empty_cache(f"nse_sync_failed::{type(exc).__name__}: {exc}")
            fallback["status"] = "stale_or_unavailable"
            fallback["last_sync_error"] = f"{type(exc).__name__}: {exc}"
            fallback["last_sync_error_at_utc"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            try:
                StorageService.save_snapshot(self.config.market_calendar_cache_path, fallback)
            except Exception:
                pass
            return fallback

    def _forced_status(self) -> Optional[Dict[str, Any]]:
        if self._env_bool("MARKET_FORCE_OPEN", False):
            return {"is_trading_day": True, "reason": "forced_open", "source": "MARKET_FORCE_OPEN"}
        if self._env_bool("MARKET_FORCE_CLOSED", False):
            return {"is_trading_day": False, "reason": "forced_closed", "source": "MARKET_FORCE_CLOSED"}
        return None

    def _manual_holidays(self) -> Set[str]:
        values: Set[str] = set()
        env_values = os.getenv("MARKET_HOLIDAY_DATES", "")
        values.update(item.strip() for item in env_values.split(",") if item.strip())

        path = self.config.market_holidays_path
        payload = StorageService.load_snapshot(path)
        if isinstance(payload, dict):
            dates = payload.get("holidays") or payload.get("holiday_dates") or []
            if isinstance(dates, list):
                values.update(str(item).strip() for item in dates if str(item).strip())
        return values

    def _load_or_refresh_nse_cache(self) -> Dict[str, Any]:
        payload = StorageService.load_snapshot(self.config.market_calendar_cache_path)
        if not payload or self._cache_is_stale(payload):
            return self.refresh_nse_holidays(force=False)
        return payload

    def _cache_is_stale(self, payload: Dict[str, Any]) -> bool:
        generated_at = payload.get("generated_at_utc")
        if not generated_at:
            return True
        try:
            generated = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        except ValueError:
            return True
        if generated.tzinfo is None:
            age = datetime.utcnow() - generated
        else:
            age = datetime.now(generated.tzinfo) - generated
        return age.total_seconds() > self.cache_ttl_seconds

    def _holiday_dates_from_cache(self, payload: Optional[Dict[str, Any]]) -> Set[str]:
        if not payload:
            return set()
        dates = payload.get("holiday_dates")
        if not isinstance(dates, list):
            return set()
        return {str(item).strip() for item in dates if str(item).strip()}

    def _cache_metadata(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not payload:
            return {"status": "missing"}
        return {
            "status": payload.get("status"),
            "source": payload.get("source"),
            "generated_at_utc": payload.get("generated_at_utc"),
            "holiday_count": len(payload.get("holiday_dates") or []),
            "last_sync_error": payload.get("last_sync_error"),
        }

    def _extract_dates(self, payload: Any) -> Set[str]:
        dates: Set[str] = set()
        for value in self._walk_values(payload):
            if not isinstance(value, str):
                continue
            parsed = self._parse_date(value)
            if parsed:
                dates.add(parsed)
        return dates

    def _walk_values(self, value: Any) -> Iterable[Any]:
        if isinstance(value, dict):
            for nested in value.values():
                yield from self._walk_values(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from self._walk_values(nested)
        else:
            yield value

    def _parse_date(self, value: str) -> Optional[str]:
        text = value.strip()
        formats = ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        return match.group(1) if match else None

    def _count_holiday_groups(self, payload: Any) -> int:
        if isinstance(payload, dict):
            return sum(1 for value in payload.values() if isinstance(value, list))
        return 0

    def _empty_cache(self, status: str) -> Dict[str, Any]:
        return {
            "stage": "market_calendar_cache",
            "source": "local_weekday_fallback",
            "source_url": None,
            "generated_at_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "status": status,
            "holiday_dates": [],
        }

    def _open_time(self) -> str:
        return f"{self.config.market_open_hour:02d}:{self.config.market_open_minute:02d}"

    def _close_time(self) -> str:
        return f"{self.config.market_close_hour:02d}:{self.config.market_close_minute:02d}"

    def _datetime_for_time(self, value: dt_time) -> datetime:
        now = self.market_time.now()
        return datetime.combine(now.date(), value, tzinfo=self.market_time.tz)

    def _time_from_hhmm(self, value: str) -> dt_time:
        hour, minute = str(value).split(":", 1)
        return dt_time(int(hour), int(minute))

    def _env_bool(self, key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
