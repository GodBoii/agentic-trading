"""Stage 1: historical-only, venue-aware Indian equity universe construction."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from pipeline.config import PipelineConfig
from pipeline.contracts import UNIVERSE_BASELINE_SCHEMA_VERSION
from pipeline.models import UniverseRecord, VenueIdentity
from pipeline.services.dhan_service import DhanService
from pipeline.services.corporate_action_service import (
    CorporateActionService,
    action_for_stock,
    action_index,
)
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class MasterValidationError(RuntimeError):
    pass


class UniverseScanner:
    MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
    REQUIRED_COLUMNS = {
        "EXCH_ID",
        "SEGMENT",
        "SECURITY_ID",
        "ISIN",
        "INSTRUMENT",
        "SYMBOL_NAME",
        "DISPLAY_NAME",
        "INSTRUMENT_TYPE",
        "SERIES",
        "ASM_GSM_FLAG",
        "BUY_SELL_INDICATOR",
    }
    ALLOWED_SERIES = {"NSE": {"EQ"}, "BSE": {"A", "B", "X"}}
    BASELINE_SCHEMA_VERSION = UNIVERSE_BASELINE_SCHEMA_VERSION

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config)
        self.market_time = MarketTimeService(self.config)
        self.corporate_actions = CorporateActionService(self.config)
        self.exclusions: List[Dict[str, Any]] = []
        self.failure_counts: Counter[str] = Counter()

    def _log(self, message: str) -> None:
        """Emit one timestamped, immediately visible operational message."""
        print(
            f"[{self.market_time.now().strftime('%Y-%m-%d %H:%M:%S %Z')}] "
            f"[Universe Scanner] {message}",
            flush=True,
        )

    def _require_data_access(self) -> None:
        profile = self.dhan.fetch_user_profile()
        if str(profile.get("status") or "").strip().lower() != "success":
            raise RuntimeError(f"Dhan profile check failed: {profile.get('remarks')}")
        data = profile.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        if (
            not isinstance(data, dict)
            or str(data.get("dataPlan") or "").strip().lower() != "active"
        ):
            raise RuntimeError("Dhan Data API subscription is not active.")

    @staticmethod
    def _text(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        return str(value).strip()

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
            return parsed if np.isfinite(parsed) else None
        except (TypeError, ValueError):
            return None

    def _download_master(self, market_date: str) -> Tuple[Path, Dict[str, Any]]:
        output_dir = self.config.security_master_reference_dir / market_date
        output_path = output_dir / "master.csv"
        source_url = os.getenv("DHAN_DETAILED_MASTER_URL", self.MASTER_URL)
        attempts = max(1, int(os.getenv("UNIVERSE_MASTER_DOWNLOAD_RETRIES", "3")))
        last_error = ""
        for attempt in range(attempts):
            try:
                response = requests.get(source_url, timeout=60, allow_redirects=True)
                response.raise_for_status()
                if len(response.content) < 1_000_000:
                    raise MasterValidationError("downloaded master is implausibly small")
                output_dir.mkdir(parents=True, exist_ok=True)
                descriptor, temp_name = tempfile.mkstemp(
                    prefix=".master.", suffix=".csv.tmp", dir=str(output_dir)
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(response.content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, output_path)
                return output_path, {
                    "source": "dhan_download",
                    "source_url": source_url,
                    "resolved_url": response.url,
                    "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                    "degraded": False,
                }
            except Exception as exc:
                last_error = f"{type(exc).__name__}:{exc}"
                if attempt + 1 < attempts:
                    time.sleep(2**attempt)

        fallback = self.config.security_master_path
        if not fallback.exists():
            raise FileNotFoundError(f"Dhan master unavailable and fallback is missing: {last_error}")
        age_hours = max(0.0, (time.time() - fallback.stat().st_mtime) / 3600)
        return fallback, {
            "source": "last_known_good",
            "source_url": source_url,
            "download_error": last_error,
            "fallback_path": str(fallback),
            "fallback_age_hours": round(age_hours, 2),
            "degraded": True,
            "fallback_within_max_age": age_hours <= self.config.stage1_master_max_age_hours,
        }

    def _read_and_validate_master(self, path: Path) -> pd.DataFrame:
        frame = pd.read_csv(path, low_memory=False)
        frame = frame.loc[:, ~frame.columns.astype(str).str.match(r"^Unnamed")]
        frame.columns = [str(column).strip().upper() for column in frame.columns]
        missing = sorted(self.REQUIRED_COLUMNS - set(frame.columns))
        if missing:
            raise MasterValidationError(f"Dhan master is missing required columns: {missing}")
        if len(frame) < 10_000:
            raise MasterValidationError(f"Dhan master row count is suspicious: {len(frame)}")
        for column in (
            "EXCH_ID",
            "SEGMENT",
            "ISIN",
            "INSTRUMENT",
            "INSTRUMENT_TYPE",
            "SERIES",
            "ASM_GSM_FLAG",
            "BUY_SELL_INDICATOR",
        ):
            frame[column] = frame[column].fillna("").astype(str).str.strip().str.upper()
        return frame

    def _eligible_venue_rows(self, frame: pd.DataFrame) -> pd.DataFrame:
        common = frame[
            frame["EXCH_ID"].isin(["NSE", "BSE"])
            & (frame["SEGMENT"] == "E")
            & (frame["INSTRUMENT"] == "EQUITY")
            & (frame["INSTRUMENT_TYPE"] == "ES")
        ].copy()

        missing_identity = common[
            (common["ISIN"] == "") | pd.to_numeric(common["SECURITY_ID"], errors="coerce").isna()
        ]
        self.failure_counts["missing_identity"] += len(missing_identity)
        common = common.drop(missing_identity.index)

        unsupported = common[
            ~(
                ((common["EXCH_ID"] == "NSE") & common["SERIES"].isin(self.ALLOWED_SERIES["NSE"]))
                | ((common["EXCH_ID"] == "BSE") & common["SERIES"].isin(self.ALLOWED_SERIES["BSE"]))
            )
        ]
        self.failure_counts["unsupported_series"] += len(unsupported)
        common = common.drop(unsupported.index)

        surveillance = common[common["ASM_GSM_FLAG"] != "N"]
        self.failure_counts["asm_gsm"] += len(surveillance)
        for _, row in surveillance.iterrows():
            self.exclusions.append(
                {
                    "reason": "ASM_GSM",
                    "isin": row["ISIN"],
                    "exchange": row["EXCH_ID"],
                    "security_id": int(float(row["SECURITY_ID"])),
                    "flag": row["ASM_GSM_FLAG"],
                    "category": self._text(row.get("ASM_GSM_CATEGORY")),
                }
            )
        common = common.drop(surveillance.index)

        disabled = common[~common["BUY_SELL_INDICATOR"].isin(["A", "Y", "B"])]
        self.failure_counts["not_tradable"] += len(disabled)
        common = common.drop(disabled.index)
        return common

    def _row_to_venue(self, row: pd.Series) -> Dict[str, Any]:
        exchange = self._text(row["EXCH_ID"])
        return {
            "exchange": exchange,
            "exchange_segment": f"{exchange}_EQ",
            "security_id": int(float(row["SECURITY_ID"])),
            "series": self._text(row["SERIES"]),
            "trading_symbol": self._text(row.get("SYMBOL_NAME")),
            "tick_size": self._number(row.get("TICK_SIZE")),
            "upper_circuit": self._number(row.get("SM_UPPER_LIMIT")),
            "lower_circuit": self._number(row.get("SM_LOWER_LIMIT")),
        }

    def _daily_frame(self, venue: Dict[str, Any]) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        cache_path = (
            self.config.results_dir
            / "reference"
            / "historical-daily"
            / str(venue["exchange_segment"])
            / f"{venue['security_id']}.parquet"
        )
        try:
            if cache_path.exists():
                cached = pd.read_parquet(cache_path)
                cached["timestamp"] = pd.to_datetime(cached["timestamp"], utc=True, errors="coerce")
                cached_market_dates = cached["timestamp"].dt.tz_convert(self.market_time.tz).dt.date
                if (
                    not cached.empty
                    and cached_market_dates.max() < self.market_time.now().date()
                    and datetime.fromtimestamp(cache_path.stat().st_mtime, timezone.utc)
                    .astimezone(self.market_time.tz)
                    .date()
                    == self.market_time.now().date()
                ):
                    return cached, None if len(cached) >= self.config.stage1_min_valid_sessions else "insufficient_history"
            response = self.dhan.fetch_daily_history(
                int(venue["security_id"]),
                days=self.config.stage1_history_days,
                retries=3,
                exchange_segment=str(venue["exchange_segment"]),
                instrument_candidates=["EQUITY"],
            )
            if not response or str(response.get("status") or "").lower() != "success":
                return None, str((response or {}).get("remarks") or "historical_fetch_failed")
            frame = self.dhan.daily_response_to_df(response)
            if frame.empty:
                return None, "no_historical_data"
            today = self.market_time.now().date()
            frame = frame[frame["timestamp"].dt.date < today].copy()
            frame = frame.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
            numeric = ["open", "high", "low", "close", "volume"]
            frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
            invalid = (
                frame[numeric].isna().any(axis=1)
                | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
                | (frame["volume"] < 0)
                | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
                | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
            )
            frame = frame[~invalid].copy()
            if not frame.empty:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = cache_path.with_name(f".{cache_path.name}.{os.getpid()}.tmp")
                frame.to_parquet(temp_path, index=False, compression="zstd")
                os.replace(temp_path, cache_path)
            if len(frame) < self.config.stage1_min_valid_sessions:
                return frame, "insufficient_history"
            return frame, None
        except Exception as exc:
            return None, f"{type(exc).__name__}:{exc}"

    def _venue_metrics(self, frame: pd.DataFrame) -> Dict[str, Any]:
        tail20 = frame.tail(20).copy()
        traded_value = tail20["close"] * tail20["volume"]
        previous_close = float(tail20["close"].iloc[-1])
        previous = frame["close"].shift(1)
        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous).abs(),
                (frame["low"] - previous).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr14 = float(true_range.tail(14).mean())
        return {
            "previous_close": round(previous_close, 4),
            "last_close_date": frame["timestamp"].iloc[-1].date().isoformat(),
            "valid_sessions": int(len(frame)),
            "active_session_ratio": round(float((tail20["volume"] > 0).mean()), 4),
            "adv_20_cr": round(float(traded_value.mean() / 10_000_000), 4),
            "median_daily_value_20_cr": round(float(traded_value.median() / 10_000_000), 4),
            "median_volume_20": int(tail20["volume"].median()),
            "avg_volume_20": int(tail20["volume"].mean()),
            "atr_14": round(atr14, 4),
            "atr_percent": round((atr14 / previous_close) * 100, 4) if previous_close else 0.0,
        }

    def _previous_selected_segments(self) -> Dict[str, str]:
        payload = StorageService.load_snapshot(self.config.stage1_latest_path) or {}
        return {
            str(stock.get("isin")): str(stock.get("exchange_segment"))
            for stock in payload.get("stocks", [])
            if stock.get("isin") and stock.get("exchange_segment")
        }

    def _scan_isin(
        self,
        isin: str,
        group: pd.DataFrame,
        previous_segments: Dict[str, str],
    ) -> Tuple[Optional[UniverseRecord], List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        comparisons: List[Dict[str, Any]] = []
        valid: List[Tuple[pd.Series, Dict[str, Any], pd.DataFrame, Dict[str, Any]]] = []
        for _, row in group.iterrows():
            venue = self._row_to_venue(row)
            frame, error = self._daily_frame(venue)
            comparison = {**venue, "isin": isin, "error": error}
            if frame is not None and not frame.empty:
                metrics = self._venue_metrics(frame)
                comparison.update(metrics)
                valid.append((row, venue, frame, metrics))
            comparisons.append(comparison)
        previous_segment = previous_segments.get(isin)
        if valid:
            valid.sort(
                key=lambda item: (
                    float(item[3]["median_daily_value_20_cr"]),
                    float(item[3]["active_session_ratio"]),
                    float(item[3]["median_volume_20"]),
                ),
                reverse=True,
            )
            selected = valid[0]
            previous = next(
                (item for item in valid if item[1]["exchange_segment"] == previous_segment),
                None,
            )
            reason = "higher_median_traded_value"
            if previous and previous is not selected:
                challenger_value = float(selected[3]["median_daily_value_20_cr"])
                previous_value = float(previous[3]["median_daily_value_20_cr"])
                if challenger_value < previous_value * self.config.stage1_venue_switch_ratio:
                    selected = previous
                    reason = "venue_hysteresis_kept_previous"
            row, venue, _frame, metrics = selected
            metrics = {
                **metrics,
                "status": (
                    "ready"
                    if int(metrics.get("valid_sessions") or 0) >= self.config.stage1_min_valid_sessions
                    else "partial"
                ),
            }
            if metrics["status"] == "partial":
                self.failure_counts["insufficient_history"] += 1
        else:
            # Historical profiles improve ranking but are not a prerequisite for
            # observing a broker-tradable equity. Prefer the prior venue, then NSE.
            rows = [item for _, item in group.iterrows()]
            row = next(
                (
                    item
                    for item in rows
                    if f"{self._text(item.get('EXCH_ID'))}_EQ" == previous_segment
                ),
                None,
            )
            if row is None:
                row = sorted(
                    rows,
                    key=lambda item: 0 if self._text(item.get("EXCH_ID")) == "NSE" else 1,
                )[0]
            venue = self._row_to_venue(row)
            metrics = {
                "status": "unavailable",
                "previous_close": None,
                "last_close_date": None,
                "valid_sessions": 0,
                "active_session_ratio": 0.0,
                "adv_20_cr": 0.0,
                "median_daily_value_20_cr": 0.0,
                "median_volume_20": 0,
                "avg_volume_20": 0,
                "atr_14": 0.0,
                "atr_percent": 0.0,
            }
            reason = "previous_or_nse_venue_without_history"
            errors = [str(item.get("error") or "") for item in comparisons]
            if errors and all(error == "insufficient_history" for error in errors):
                self.failure_counts["insufficient_history"] += 1
            else:
                self.failure_counts["historical_fetch_failed"] += 1

        if self.config.stage1_apply_opportunity_filters:
            passed = (
                self.config.stage1_min_price <= float(metrics["previous_close"] or 0.0) <= self.config.stage1_max_price
                and float(metrics["adv_20_cr"] or 0.0) >= self.config.stage1_min_adv_cr
                and float(metrics["atr_percent"] or 0.0) >= self.config.stage1_min_atr_percent
                and float(metrics["active_session_ratio"] or 0.0) >= self.config.stage1_min_active_session_ratio
            )
            if not passed:
                return None, comparisons, {
                    "reason": "LEGACY_OPPORTUNITY_FILTER",
                    "isin": isin,
                    "selected_venue": venue,
                    "historical": metrics,
                }

        identity = VenueIdentity(
            exchange=venue["exchange"],
            exchange_segment=venue["exchange_segment"],
            security_id=venue["security_id"],
            series=venue["series"],
            trading_symbol=venue["trading_symbol"],
        )
        alternates = [
            item
            for item in comparisons
            if int(item["security_id"]) != int(venue["security_id"])
        ]
        record = UniverseRecord(
            isin=isin,
            symbol=self._text(row.get("SYMBOL_NAME")),
            display_name=self._text(row.get("DISPLAY_NAME")) or self._text(row.get("SYMBOL_NAME")),
            instrument="EQUITY",
            instrument_type="ES",
            selected_venue=identity,
            selected_venue_reason=reason,
            alternate_venues=alternates,
            historical=metrics,
            surveillance={
                "asm_gsm_flag": self._text(row.get("ASM_GSM_FLAG")),
                "category": self._text(row.get("ASM_GSM_CATEGORY")),
            },
            tradability={
                "buy_sell_indicator": self._text(row.get("BUY_SELL_INDICATOR")),
                "tick_size": venue.get("tick_size"),
                "lot_size": self._number(row.get("LOT_SIZE")),
                "bracket_order_eligible": self._text(row.get("BRACKET_FLAG")),
                "cover_order_eligible": self._text(row.get("COVER_FLAG")),
                "mtf_leverage": self._number(row.get("MTF_LEVERAGE")),
                "upper_circuit": venue.get("upper_circuit"),
                "lower_circuit": venue.get("lower_circuit"),
                "freeze_quantity": self._number(row.get("SM_FREEZE_QTY")),
            },
        )
        return record, comparisons, None

    def _intraday_baseline(self, record: UniverseRecord) -> Dict[str, Any]:
        if os.getenv("UNIVERSE_SCANNER_BUILD_INTRADAY_BASELINES", "1").strip().lower() in {"0", "false", "no"}:
            return {"status": "disabled"}
        cache_path = (
            self.config.results_dir
            / "reference"
            / "intraday-baselines"
            / record.selected_venue.exchange_segment
            / f"{record.selected_venue.security_id}.json"
        )
        cached = StorageService.load_snapshot(cache_path)
        if cached and cached.get("status") == "ready":
            try:
                generated = datetime.fromisoformat(str(cached["generated_at_utc"]).replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - generated.astimezone(timezone.utc)
                if age.days < self.config.stage1_intraday_baseline_cache_days:
                    return {**cached, "schema_version": self.BASELINE_SCHEMA_VERSION}
            except (KeyError, TypeError, ValueError):
                pass
        try:
            response = self.dhan.fetch_intraday_history(
                record.selected_venue.security_id,
                days=30,
                interval=5,
                retries=3,
                exchange_segment=record.selected_venue.exchange_segment,
                instrument_candidates=["EQUITY"],
            )
            if not response or str(response.get("status") or "").lower() != "success":
                return {"status": "unavailable"}
            frame = self.dhan.intraday_response_to_df(response)
            if frame.empty:
                return {"status": "unavailable"}
            timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
            frame["timestamp"] = timestamps.dt.tz_convert(self.market_time.tz)
            frame = frame.dropna(subset=["timestamp"])
            frame = frame[frame["timestamp"].dt.date < self.market_time.now().date()].copy()
            frame["minute"] = frame["timestamp"].dt.strftime("%H:%M")
            frame["session"] = frame["timestamp"].dt.date.astype(str)
            frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
            frame["cumulative_volume"] = frame.groupby("session")["volume"].cumsum()
            frame["range_percent"] = (
                (pd.to_numeric(frame["high"], errors="coerce") - pd.to_numeric(frame["low"], errors="coerce"))
                / pd.to_numeric(frame["close"], errors="coerce").replace(0, np.nan)
                * 100
            )
            expected_interval = frame.groupby("minute")["volume"].median()
            expected_cumulative = frame.groupby("minute")["cumulative_volume"].median()
            volatility_by_minute = frame.groupby("minute")["range_percent"].median().dropna()
            opening = frame[frame["minute"].isin(["09:15", "09:20", "09:25"])].copy()
            opening_ranges: List[float] = []
            for _, session_frame in opening.groupby("session"):
                first_open = self._number(session_frame.iloc[0].get("open"))
                if first_open and first_open > 0:
                    opening_ranges.append(
                        (
                            float(session_frame["high"].max())
                            - float(session_frame["low"].min())
                        )
                        / first_open
                        * 100
                    )
            sessions = int(frame["session"].nunique())
            captured = getattr(self, "captured_live_baselines", {}).get(
                record.selected_venue.security_id,
                {},
            )
            result = {
                "status": "ready",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "timezone": str(self.market_time.tz),
                "schema_version": self.BASELINE_SCHEMA_VERSION,
                "interval_minutes": 5,
                "sessions": sessions,
                "median_interval_volume": {str(k): round(float(v), 2) for k, v in expected_interval.items()},
                "median_cumulative_volume": {str(k): round(float(v), 2) for k, v in expected_cumulative.items()},
                "median_opening_range_percent": (
                    round(float(np.median(opening_ranges)), 4) if opening_ranges else None
                ),
                "median_range_percent_by_minute": {
                    str(k): round(float(v), 4) for k, v in volatility_by_minute.items()
                },
                "captured_live_liquidity": captured,
            }
            StorageService.save_snapshot(cache_path, result)
            return result
        except Exception:
            return {"status": "unavailable"}

    def refresh_intraday_baselines(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upgrade a valid daily universe without repeating the full master scan."""

        stocks = payload.get("stocks") or []
        if not stocks:
            raise RuntimeError("Cannot refresh intraday baselines for an empty universe.")
        self.captured_live_baselines = self._load_captured_live_baselines()

        def as_record(stock: Dict[str, Any]) -> UniverseRecord:
            venue = VenueIdentity(
                exchange=str(stock["exchange"]),
                exchange_segment=str(stock["exchange_segment"]),
                security_id=int(stock["security_id"]),
                series=str(stock.get("series") or ""),
                trading_symbol=str(stock.get("trading_symbol") or stock.get("symbol") or ""),
            )
            return UniverseRecord(
                isin=str(stock["isin"]),
                symbol=str(stock.get("symbol") or ""),
                display_name=str(stock.get("display_name") or stock.get("symbol") or ""),
                instrument=str(stock.get("instrument") or "EQUITY"),
                instrument_type=str(stock.get("instrument_type") or "ES"),
                selected_venue=venue,
                selected_venue_reason=str(stock.get("selected_venue_reason") or ""),
                alternate_venues=list(stock.get("alternate_venues") or []),
                historical=dict(stock.get("historical") or {}),
                surveillance=dict(stock.get("surveillance") or {}),
                tradability=dict(stock.get("tradability") or {}),
            )

        workers = max(1, min(4, self.config.stage1_workers))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._intraday_baseline, as_record(stock)): stock
                for stock in stocks
            }
            for future in as_completed(futures):
                futures[future]["intraday_baselines"] = future.result()

        summary = payload.setdefault("summary", {})
        market_date = str(summary.get("market_date") or self.market_time.market_date_str())
        old_version = str(summary.get("universe_version") or market_date)
        base_version = old_version.rsplit("-b", 1)[0] if old_version.rsplit("-b", 1)[-1].isdigit() else old_version
        summary["universe_version"] = f"{base_version}-b{self.BASELINE_SCHEMA_VERSION}"
        summary["baseline_schema_version"] = self.BASELINE_SCHEMA_VERSION
        summary["baselines_ready"] = sum(
            (stock.get("intraday_baselines") or {}).get("status") == "ready"
            for stock in stocks
        )
        summary["baselines_unavailable"] = len(stocks) - int(summary["baselines_ready"])
        summary["baselines_refreshed_at_utc"] = datetime.now(timezone.utc).isoformat()
        payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        StorageService.save_snapshot(self.config.stage1_daily_path(market_date), payload)
        StorageService.save_snapshot(self.config.stage1_latest_path, payload)
        self._save_parquet_atomic(
            self.config.stage1_universe_parquet_path(market_date),
            pd.json_normalize(stocks),
        )
        return payload

    def _load_captured_live_baselines(self) -> Dict[int, Dict[str, Any]]:
        observations: Dict[int, Dict[str, List[float]]] = {}
        root = self.config.stage2_results_dir
        if not root.exists():
            return {}
        dated = sorted(
            (path for path in root.iterdir() if path.is_dir()),
            reverse=True,
        )[: self.config.intra_finder_derived_retention_days]
        for date_dir in dated:
            payload = (
                StorageService.load_snapshot(date_dir / "latest-state.json")
                or StorageService.load_snapshot(date_dir / "features" / "latest.json")
                or {}
            )
            for stock in payload.get("stocks") or []:
                try:
                    security_id = int(stock["security_id"])
                except (KeyError, TypeError, ValueError):
                    continue
                features = stock.get("features") or {}
                bucket = observations.setdefault(
                    security_id,
                    {"spread_percent": [], "bid_quantity_5": [], "ask_quantity_5": []},
                )
                for key in bucket:
                    value = self._number(features.get(key))
                    if value is not None:
                        bucket[key].append(value)
        result: Dict[int, Dict[str, Any]] = {}
        for security_id, values in observations.items():
            result[security_id] = {
                "sessions_observed": max((len(items) for items in values.values()), default=0),
                "median_spread_percent": (
                    round(float(np.median(values["spread_percent"])), 5)
                    if values["spread_percent"]
                    else None
                ),
                "median_bid_quantity_5": (
                    round(float(np.median(values["bid_quantity_5"])), 2)
                    if values["bid_quantity_5"]
                    else None
                ),
                "median_ask_quantity_5": (
                    round(float(np.median(values["ask_quantity_5"])), 2)
                    if values["ask_quantity_5"]
                    else None
                ),
            }
        return result

    @staticmethod
    def _save_parquet_atomic(path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        frame.to_parquet(temp_path, index=False, compression="zstd")
        os.replace(temp_path, path)

    def run(self, max_isins: Optional[int] = None) -> Dict[str, Any]:
        started = time.time()
        market_date = self.market_time.market_date_str()
        corporate_action_payload = self.corporate_actions.actions_for_date(market_date)
        corporate_actions = action_index(corporate_action_payload)
        self._log(
            "Starting Stage 1 historical universe build. Live quotes are not used in this stage."
        )
        self._require_data_access()
        self._log("Downloading and validating Dhan's detailed instrument master.")
        master_path, master_meta = self._download_master(market_date)
        try:
            frame = self._read_and_validate_master(master_path)
            previous_payload = StorageService.load_snapshot(self.config.stage1_latest_path) or {}
            previous_rows = (
                ((previous_payload.get("summary") or {}).get("master") or {}).get("rows")
            )
            if previous_rows and len(frame) < int(previous_rows) * 0.70:
                raise MasterValidationError(
                    f"Dhan master row count dropped from {previous_rows} to {len(frame)}"
                )
        except MasterValidationError as exc:
            fallback = self.config.security_master_path
            if master_path.resolve() == fallback.resolve() or not fallback.exists():
                raise
            master_meta = {
                "source": "last_known_good",
                "source_url": master_meta.get("source_url"),
                "download_validation_error": str(exc),
                "fallback_path": str(fallback),
                "fallback_age_hours": round(
                    max(0.0, (time.time() - fallback.stat().st_mtime) / 3600),
                    2,
                ),
                "degraded": True,
            }
            master_path = fallback
            frame = self._read_and_validate_master(master_path)
        self._log(
            f"Instrument master ready: source={master_meta.get('source')}, "
            f"rows={len(frame):,}, degraded={bool(master_meta.get('degraded'))}."
        )
        checksum = hashlib.sha256(master_path.read_bytes()).hexdigest()
        eligible = self._eligible_venue_rows(frame)
        groups = list(eligible.groupby("ISIN", sort=True))
        if max_isins:
            groups = groups[:max_isins]
        previous_segments = self._previous_selected_segments()
        self._log(
            f"Cash-equity filtering complete: eligible venue rows={len(eligible):,}, "
            f"unique ISINs={len(groups):,}, duplicate venue rows={max(0, len(eligible) - len(groups)):,}, "
            f"ASM/GSM excluded={int(self.failure_counts['asm_gsm']):,}."
        )
        records: List[UniverseRecord] = []
        comparisons: List[Dict[str, Any]] = []
        historical_exclusions: List[Dict[str, Any]] = []

        workers = max(1, int(os.getenv("UNIVERSE_SCANNER_WORKERS", str(self.config.stage1_workers))))
        completed_history = 0
        history_total = len(groups)
        self._log(
            f"Loading completed daily history and comparing NSE/BSE liquidity with {workers} workers."
        )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._scan_isin, isin, group, previous_segments): isin
                for isin, group in groups
            }
            for future in as_completed(futures):
                record, venue_rows, exclusion = future.result()
                completed_history += 1
                comparisons.extend(venue_rows)
                if record:
                    records.append(record)
                if exclusion:
                    historical_exclusions.append(exclusion)
                    self.failure_counts[str(exclusion["reason"]).lower()] += 1
                if completed_history == history_total or completed_history % 250 == 0:
                    self._log(
                        f"Historical scan progress: {completed_history:,}/{history_total:,} ISINs; "
                        f"current survivors={len(records):,}, exclusions={len(historical_exclusions):,}."
                    )

        self.captured_live_baselines = self._load_captured_live_baselines()
        baseline_workers = max(1, min(4, workers))
        completed_baselines = 0
        self._log(
            f"Preparing five-minute historical intraday baselines for {len(records):,} survivors."
        )
        with ThreadPoolExecutor(max_workers=baseline_workers) as executor:
            futures = {executor.submit(self._intraday_baseline, record): record for record in records}
            for future in as_completed(futures):
                record = futures[future]
                record.intraday_baselines = future.result()
                completed_baselines += 1
                if completed_baselines == len(records) or completed_baselines % 100 == 0:
                    ready = sum(
                        (item.intraday_baselines or {}).get("status") == "ready"
                        for item in records
                    )
                    self._log(
                        f"Baseline progress: {completed_baselines:,}/{len(records):,}; ready={ready:,}."
                    )

        stock_rows = [record.as_dict() for record in records]
        for stock in stock_rows:
            stock["corporate_action"] = action_for_stock(corporate_actions, stock)
        stock_rows.sort(key=lambda item: float(item["historical"]["adv_20_cr"]), reverse=True)
        version = f"{market_date}-{checksum[:12]}-b2"
        degraded_reasons = []
        if master_meta.get("degraded"):
            degraded_reasons.append("stale_master_fallback")
        fetch_failure_ratio = (
            self.failure_counts["historical_fetch_failed"] / history_total
            if history_total
            else 1.0
        )
        # Historical profiles are optional ranking context in the full-universe
        # architecture. Master/reference corruption still degrades publication;
        # per-stock history failures remain visible without removing instruments.
        status = "degraded" if degraded_reasons else "completed"
        summary = {
            "status": status,
            "market_date": market_date,
            "universe_version": version,
            "master": {**master_meta, "checksum_sha256": checksum, "rows": len(frame)},
            "eligible_venue_rows": len(eligible),
            "unique_isins_scanned": len(groups),
            "duplicate_venue_rows": max(0, len(eligible) - len(groups)),
            "asm_gsm_excluded": int(self.failure_counts["asm_gsm"]),
            "insufficient_history_count": int(self.failure_counts["insufficient_history"]),
            "historical_fetch_failed": int(self.failure_counts["historical_fetch_failed"]),
            "historical_fetch_failure_ratio": round(fetch_failure_ratio, 6),
            "historical_profiles_ready": sum(
                (row.get("historical") or {}).get("status") == "ready" for row in stock_rows
            ),
            "historical_profiles_unavailable": sum(
                (row.get("historical") or {}).get("status") != "ready" for row in stock_rows
            ),
            "opportunity_filters_applied": self.config.stage1_apply_opportunity_filters,
            "corporate_actions": {
                "status": corporate_action_payload.get("status"),
                "matched_stocks": sum(bool(row.get("corporate_action")) for row in stock_rows),
                "source_errors": corporate_action_payload.get("source_errors") or [],
            },
            "stage1_passed": len(stock_rows),
            "venue_selections": dict(Counter(row["exchange"] for row in stock_rows)),
            "exclusion_reason_counts": dict(self.failure_counts),
            "degraded_reasons": degraded_reasons,
            "historical_data_cutoff": self.market_time.now().date().isoformat(),
            "baseline_schema_version": self.BASELINE_SCHEMA_VERSION,
            "baselines_ready": sum(
                (row.get("intraday_baselines") or {}).get("status") == "ready"
                for row in stock_rows
            ),
            "baselines_unavailable": sum(
                (row.get("intraday_baselines") or {}).get("status") != "ready"
                for row in stock_rows
            ),
            "elapsed_seconds": round(time.time() - started, 2),
            "filters": {
                "mode": (
                    "legacy_opportunity_filters"
                    if self.config.stage1_apply_opportunity_filters
                    else "tradable_universe_only"
                ),
                "price": [self.config.stage1_min_price, self.config.stage1_max_price],
                "adv_20_cr_min": self.config.stage1_min_adv_cr,
                "atr_percent_min": self.config.stage1_min_atr_percent,
                "valid_sessions_min": self.config.stage1_min_valid_sessions,
                "active_session_ratio_min": self.config.stage1_min_active_session_ratio,
            },
        }
        payload = StorageService.build_payload("universe_scanner", summary, "stocks", stock_rows)
        destination = (
            self.config.stage1_degraded_path(market_date)
            if status == "degraded"
            else self.config.stage1_daily_path(market_date)
        )
        StorageService.save_snapshot(destination, payload)
        StorageService.save_snapshot(
            self.config.stage1_exclusions_path(market_date),
            {"market_date": market_date, "exclusions": self.exclusions + historical_exclusions},
        )
        StorageService.save_snapshot(self.config.stage1_run_report_path(market_date), summary)
        if stock_rows:
            self._save_parquet_atomic(
                self.config.stage1_universe_parquet_path(market_date),
                pd.json_normalize(stock_rows),
            )
        if comparisons:
            self._save_parquet_atomic(
                self.config.stage1_venue_comparison_path(market_date),
                pd.json_normalize(comparisons),
            )
        if status == "completed":
            StorageService.save_snapshot(self.config.stage1_latest_path, payload)
        self._log(
            f"Stage 1 {status}: passed={len(stock_rows):,}, "
            f"NSE={summary['venue_selections'].get('NSE', 0):,}, "
            f"BSE={summary['venue_selections'].get('BSE', 0):,}, "
            f"baselines_ready={summary['baselines_ready']:,}, "
            f"fetch_failures={summary['historical_fetch_failed']:,}, "
            f"elapsed={summary['elapsed_seconds']:.2f}s."
        )
        self._log(f"Published universe version {version} to {destination}.")
        return payload
