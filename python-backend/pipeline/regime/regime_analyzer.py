from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_reference_service import MarketReferenceService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class MarketRegimeAnalyzer:
    """
    Market-context regime analyzer.
    This lane reads market-wide sources only: indices, sector indices, index futures,
    and optional externally provided market-summary JSON files for movers/news/attention.
    It does not consume Stage 1 or any stock-selection output.
    """

    EXTERNAL_INPUT_FILES = {
        "market_breadth": "market_breadth.json",
        "market_movers": "market_movers.json",
        "market_news": "market_news.json",
        "market_attention": "market_attention.json",
        "market_derivatives": "market_derivatives.json",
    }

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config)
        self.market_time = MarketTimeService(self.config)
        self.references = MarketReferenceService(self.config)
        self.catalog = self._load_source_catalog()

    def _load_source_catalog(self) -> Dict[str, Any]:
        return json.loads(self.config.regime_source_catalog_path.read_text(encoding="utf-8"))

    def _session_state(self) -> Dict[str, Any]:
        now = self.market_time.now()
        market_open = now.replace(
            hour=self.config.market_open_hour,
            minute=self.config.market_open_minute,
            second=0,
            microsecond=0,
        )
        market_close = now.replace(
            hour=self.config.market_close_hour,
            minute=self.config.market_close_minute,
            second=0,
            microsecond=0,
        )
        minutes_since_open = max(0, int((now - market_open).total_seconds() // 60))
        minutes_to_close = max(0, int((market_close - now).total_seconds() // 60))

        if now < market_open:
            session = "pre_open"
        elif now <= market_close:
            session = "live_market"
        else:
            session = "post_market"

        return {
            "market_session": session,
            "minutes_since_open": minutes_since_open,
            "minutes_to_close": minutes_to_close,
            "is_market_hours": session == "live_market",
            "is_discovery_phase": session == "live_market"
            and minutes_since_open < self.config.regime_min_minutes_after_open,
        }

    def _resolve_index_source(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.references.find_index(source["symbol"], source["exchange"])

    def _resolve_future_source(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.references.find_front_month_future(source["exchange"], source["underlying_symbol"])

    def _today_market_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        local_ts = frame["timestamp"].dt.tz_localize("UTC").dt.tz_convert(self.market_time.tz)
        local_frame = frame.copy()
        local_frame["market_timestamp"] = local_ts
        local_frame["market_date"] = local_ts.dt.date
        today = self.market_time.now().date()
        return local_frame[local_frame["market_date"] == today].sort_values("market_timestamp")

    def _compute_intraday_vwap(self, today_frame: pd.DataFrame) -> Optional[float]:
        if today_frame.empty:
            return None
        volume = pd.to_numeric(today_frame["volume"], errors="coerce").fillna(0.0)
        total_volume = float(volume.sum())
        if math.isclose(total_volume, 0.0):
            return None
        typical_price = (
            pd.to_numeric(today_frame["high"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["low"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["close"], errors="coerce").fillna(0.0)
        ) / 3.0
        vwap = (typical_price * volume).sum() / total_volume
        return float(vwap) if pd.notna(vwap) else None

    def _compute_opening_range_break(self, today_frame: pd.DataFrame, latest_price: float) -> Dict[str, Optional[float]]:
        if today_frame.empty or "market_timestamp" not in today_frame.columns:
            return {
                "opening_range_high": None,
                "opening_range_low": None,
                "opening_range_breakout_percent": None,
                "opening_range_breakdown_percent": None,
                "opening_range_complete": False,
            }

        open_dt = datetime.combine(
            self.market_time.now().date(),
            dt_time(self.config.market_open_hour, self.config.market_open_minute),
            tzinfo=self.market_time.tz,
        )
        range_end = open_dt + timedelta(minutes=self.config.regime_opening_range_minutes)
        opening_slice = today_frame[
            (today_frame["market_timestamp"] >= open_dt)
            & (today_frame["market_timestamp"] < range_end)
        ]
        expected_bars = self.config.regime_opening_range_minutes
        opening_range_complete = len(opening_slice) >= max(3, expected_bars // 2)
        if opening_slice.empty:
            return {
                "opening_range_high": None,
                "opening_range_low": None,
                "opening_range_breakout_percent": None,
                "opening_range_breakdown_percent": None,
                "opening_range_complete": False,
            }

        opening_high = float(pd.to_numeric(opening_slice["high"], errors="coerce").max())
        opening_low = float(pd.to_numeric(opening_slice["low"], errors="coerce").min())
        breakout = ((latest_price - opening_high) / opening_high) * 100.0 if opening_high > 0 else None
        breakdown = ((opening_low - latest_price) / opening_low) * 100.0 if opening_low > 0 else None
        return {
            "opening_range_high": round(opening_high, 4),
            "opening_range_low": round(opening_low, 4),
            "opening_range_breakout_percent": round(breakout, 4) if breakout is not None else None,
            "opening_range_breakdown_percent": round(breakdown, 4) if breakdown is not None else None,
            "opening_range_complete": opening_range_complete,
        }

    def _fetch_source_snapshot(
        self,
        source_key: str,
        source_meta: Dict[str, Any],
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        exchange_segment = source_meta["exchange_segment"]
        instrument = source_meta["instrument"]
        security_id = int(source_meta["security_id"])
        resp = self.dhan.fetch_intraday_history(
            security_id,
            days=self.config.regime_history_days,
            interval=1,
            exchange_segment=exchange_segment,
            instrument_candidates=[instrument],
        )
        if not resp or str(resp.get("status", "")).lower() != "success":
            return source_key, None, "intraday_history_failed"

        frame = self.dhan.intraday_response_to_df(resp)
        if frame.empty:
            return source_key, None, "intraday_history_empty"

        today_frame = self._today_market_frame(frame)
        if today_frame.empty:
            return source_key, None, "intraday_today_empty"

        latest_price = float(pd.to_numeric(today_frame["close"], errors="coerce").iloc[-1])
        open_price = float(pd.to_numeric(today_frame["open"], errors="coerce").iloc[0])
        vwap = self._compute_intraday_vwap(today_frame)
        rvol = self.dhan.compute_time_of_day_rvol(frame)
        day_change_percent = ((latest_price - open_price) / open_price) * 100.0 if open_price > 0 else None
        price_vs_vwap_percent = ((latest_price - vwap) / vwap) * 100.0 if vwap and vwap > 0 else None
        opening_range = self._compute_opening_range_break(today_frame, latest_price)

        snapshot = {
            "name": source_meta["name"],
            "exchange": source_meta["exchange"],
            "exchange_segment": exchange_segment,
            "instrument": instrument,
            "security_id": security_id,
            "symbol": source_meta["symbol"],
            "display_name": source_meta["display_name"],
            "latest_price": round(latest_price, 4),
            "open_price": round(open_price, 4),
            "intraday_vwap": round(vwap, 4) if vwap is not None else None,
            "day_change_percent": round(day_change_percent, 4) if day_change_percent is not None else None,
            "price_vs_vwap_percent": round(price_vs_vwap_percent, 4) if price_vs_vwap_percent is not None else None,
            "time_of_day_rvol": round(rvol, 4) if rvol is not None else None,
            "latest_bar_time": today_frame["market_timestamp"].iloc[-1].isoformat(),
            "is_above_open": bool(day_change_percent is not None and day_change_percent > 0),
            "is_above_vwap": bool(price_vs_vwap_percent is not None and price_vs_vwap_percent > 0),
        }
        snapshot.update(opening_range)
        return source_key, snapshot, None

    def _load_external_market_inputs(self) -> Tuple[Dict[str, Any], Dict[str, str]]:
        payloads: Dict[str, Any] = {}
        missing: Dict[str, str] = {}
        self.config.regime_inputs_dir.mkdir(parents=True, exist_ok=True)

        for key, file_name in self.EXTERNAL_INPUT_FILES.items():
            path = self.config.regime_inputs_dir / file_name
            if not path.exists():
                missing[key] = "not_provided"
                continue
            try:
                payloads[key] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                missing[key] = f"invalid_json::{type(exc).__name__}"
        return payloads, missing

    def _resolve_market_sources(self) -> Dict[str, List[Dict[str, Any]]]:
        resolved: Dict[str, List[Dict[str, Any]]] = {
            "primary_indices": [],
            "sector_indices": [],
            "index_futures": [],
        }

        for item in self.catalog.get("primary_indices", []):
            resolved_item = self._resolve_index_source(item)
            if not resolved_item:
                continue
            resolved["primary_indices"].append({
                "name": item["name"],
                "exchange": item["exchange"],
                "symbol": item["symbol"],
                "display_name": resolved_item["display_name"],
                "exchange_segment": "IDX_I",
                "instrument": "INDEX",
                "security_id": resolved_item["security_id"],
            })

        sector_items = self.catalog.get("sector_indices", [])[: self.config.regime_sector_limit]
        for item in sector_items:
            resolved_item = self._resolve_index_source(item)
            if not resolved_item:
                continue
            resolved["sector_indices"].append({
                "name": item["name"],
                "exchange": item["exchange"],
                "symbol": item["symbol"],
                "display_name": resolved_item["display_name"],
                "exchange_segment": "IDX_I",
                "instrument": "INDEX",
                "security_id": resolved_item["security_id"],
            })

        for item in self.catalog.get("index_futures", []):
            resolved_item = self._resolve_future_source(item)
            if not resolved_item:
                continue
            resolved["index_futures"].append({
                "name": item["name"],
                "exchange": item["exchange"],
                "symbol": resolved_item["symbol"],
                "display_name": resolved_item["display_name"],
                "exchange_segment": f"{item['exchange']}_FNO" if item["exchange"] in {"NSE", "BSE"} else resolved_item["exchange_segment"],
                "instrument": "FUTIDX",
                "security_id": resolved_item["security_id"],
                "underlying_symbol": item["underlying_symbol"],
                "expiry_date": resolved_item["expiry_date"].isoformat() if resolved_item.get("expiry_date") else None,
            })
        return resolved

    def _fetch_resolved_sources(
        self,
        resolved: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        snapshots: Dict[str, Dict[str, Any]] = {}
        failures: Dict[str, str] = {}
        work_items: List[Tuple[str, Dict[str, Any]]] = []
        for group_name, items in resolved.items():
            for item in items:
                work_items.append((f"{group_name}.{item['name']}", item))

        with ThreadPoolExecutor(max_workers=self.config.regime_workers) as executor:
            futures = [
                executor.submit(self._fetch_source_snapshot, key, item)
                for key, item in work_items
            ]
            for future in as_completed(futures):
                key, snapshot, failure = future.result()
                if snapshot:
                    snapshots[key] = snapshot
                elif failure:
                    failures[key] = failure
        return snapshots, failures

    def _average(self, rows: List[Dict[str, Any]], key: str) -> Optional[float]:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def _ratio(self, rows: List[Dict[str, Any]], key: str) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if row.get(key)) / len(rows)

    def _classify_regime(
        self,
        session_state: Dict[str, Any],
        primary_indices: List[Dict[str, Any]],
        sector_indices: List[Dict[str, Any]],
        futures: List[Dict[str, Any]],
        external_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        if session_state["market_session"] == "pre_open":
            return {
                "market_regime": "pre_open",
                "confidence": 100.0,
                "reasoning_summary": "Market has not opened yet; regime is informationally unavailable until live price discovery starts.",
            }
        if session_state["market_session"] == "post_market":
            return {
                "market_regime": "post_market",
                "confidence": 100.0,
                "reasoning_summary": "Market session is closed; this snapshot is end-of-day context rather than a live trading regime.",
            }
        if session_state["is_discovery_phase"]:
            return {
                "market_regime": "open_discovery",
                "confidence": 60.0,
                "reasoning_summary": "The market is still in the opening discovery window, so structural labels remain provisional.",
            }

        vix_snapshot = next((row for row in primary_indices if row["name"] == "india_vix"), None)
        directional_indices = [row for row in primary_indices if row["name"] != "india_vix"]

        avg_primary_change = self._average(directional_indices, "day_change_percent") or 0.0
        avg_primary_vwap = self._average(directional_indices, "price_vs_vwap_percent") or 0.0
        primary_above_open = self._ratio(directional_indices, "is_above_open")
        primary_above_vwap = self._ratio(directional_indices, "is_above_vwap")
        sector_breadth = self._ratio(sector_indices, "is_above_open")
        avg_sector_change = self._average(sector_indices, "day_change_percent") or 0.0
        avg_sector_vwap = self._average(sector_indices, "price_vs_vwap_percent") or 0.0
        breakout_ratio = self._ratio(
            [row for row in directional_indices + sector_indices if row.get("opening_range_complete")],
            "is_above_vwap",
        )

        futures_alignment_score = 0.0
        if futures:
            aligned = 0
            compared = 0
            primary_map = {
                "NIFTY": next((row for row in directional_indices if row["symbol"] == "NIFTY"), None),
                "BANKNIFTY": next((row for row in directional_indices if row["symbol"] == "BANKNIFTY"), None),
                "SENSEX": next((row for row in directional_indices if row["symbol"] == "SENSEX"), None),
                "MIDCPNIFTY": next((row for row in sector_indices if row["symbol"] == "MIDCPNIFTY"), None),
            }
            for future_row in futures:
                underlying = future_row.get("underlying_symbol")
                spot_row = primary_map.get(str(underlying))
                if not spot_row:
                    continue
                future_move = float(future_row.get("day_change_percent") or 0.0)
                spot_move = float(spot_row.get("day_change_percent") or 0.0)
                if math.isclose(future_move, 0.0) or math.isclose(spot_move, 0.0):
                    continue
                compared += 1
                if (future_move > 0 and spot_move > 0) or (future_move < 0 and spot_move < 0):
                    aligned += 1
            futures_alignment_score = aligned / compared if compared else 0.0

        vix_change = float(vix_snapshot.get("day_change_percent") or 0.0) if vix_snapshot else 0.0
        event_input = external_inputs.get("market_news", {})
        news_severity = float(event_input.get("event_severity_score", 0.0) or 0.0)

        if abs(avg_primary_change) >= 0.9 or abs(vix_change) >= 8.0 or news_severity >= 0.7:
            label = "event_driven"
        elif (
            avg_primary_change >= 0.35
            and avg_primary_vwap >= 0.15
            and primary_above_open >= 0.66
            and sector_breadth >= 0.58
            and futures_alignment_score >= 0.5
        ):
            label = "trend_up"
        elif (
            avg_primary_change <= -0.35
            and avg_primary_vwap <= -0.15
            and primary_above_open <= 0.34
            and sector_breadth <= 0.42
            and futures_alignment_score >= 0.5
        ):
            label = "trend_down"
        elif avg_primary_change > 0 and sector_breadth >= 0.58 and vix_change <= 2.0:
            label = "risk_on"
        elif avg_primary_change < 0 and sector_breadth <= 0.42 and vix_change >= 2.0:
            label = "risk_off"
        elif abs(avg_primary_vwap) <= 0.12 and 0.40 <= sector_breadth <= 0.60:
            label = "mean_reversion"
        else:
            label = "choppy"

        confidence = min(
            100.0,
            45.0
            + min(abs(avg_primary_change) * 22.0, 22.0)
            + min(abs(avg_primary_vwap) * 18.0, 18.0)
            + min(abs(sector_breadth - 0.5) * 40.0, 10.0)
            + min(futures_alignment_score * 10.0, 10.0),
        )
        summary = (
            f"avg_primary_change={round(avg_primary_change, 4)}%, "
            f"avg_primary_vwap={round(avg_primary_vwap, 4)}%, "
            f"sector_breadth={round(sector_breadth, 4)}, "
            f"avg_sector_change={round(avg_sector_change, 4)}%, "
            f"avg_sector_vwap={round(avg_sector_vwap, 4)}%, "
            f"futures_alignment={round(futures_alignment_score, 4)}, "
            f"vix_change={round(vix_change, 4)}%, "
            f"breakout_ratio={round(breakout_ratio, 4)}"
        )
        return {
            "market_regime": label,
            "confidence": round(confidence, 2),
            "reasoning_summary": summary,
        }

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        StorageService.save_snapshot(self.config.regime_latest_path, payload)
        StorageService.save_snapshot(self.config.regime_daily_path(self.market_time.market_date_str()), payload)

    def run(self) -> Dict[str, Any]:
        print("=" * 60)
        print("REGIME - MARKET CONTEXT ANALYZER")
        print("=" * 60)
        print(f"Current market time: {self.market_time.market_status_text()}")

        session_state = self._session_state()
        resolved = self._resolve_market_sources()
        source_snapshots, source_failures = self._fetch_resolved_sources(resolved)
        external_inputs, external_missing = self._load_external_market_inputs()

        primary_indices = [
            source_snapshots[key]
            for key in sorted(source_snapshots)
            if key.startswith("primary_indices.")
        ]
        sector_indices = [
            source_snapshots[key]
            for key in sorted(source_snapshots)
            if key.startswith("sector_indices.")
        ]
        futures = [
            source_snapshots[key]
            for key in sorted(source_snapshots)
            if key.startswith("index_futures.")
        ]

        regime = self._classify_regime(
            session_state=session_state,
            primary_indices=primary_indices,
            sector_indices=sector_indices,
            futures=futures,
            external_inputs=external_inputs,
        )

        payload = {
            "stage": "market_regime",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "market_date": self.market_time.market_date_str(),
                "market_session": session_state["market_session"],
                "resolved_source_groups": {
                    "primary_indices": len(resolved["primary_indices"]),
                    "sector_indices": len(resolved["sector_indices"]),
                    "index_futures": len(resolved["index_futures"]),
                },
                "fetched_source_groups": {
                    "primary_indices": len(primary_indices),
                    "sector_indices": len(sector_indices),
                    "index_futures": len(futures),
                },
                "source_failures": source_failures,
                "external_inputs_missing": external_missing,
                "review_interval_seconds": self.config.regime_loop_interval_seconds,
                "next_review_at": (
                    self.market_time.now() + timedelta(seconds=self.config.regime_loop_interval_seconds)
                ).isoformat(),
            },
            "regime": {
                "status": session_state["market_session"],
                "market_regime": regime["market_regime"],
                "confidence": regime["confidence"],
                "minutes_since_open": session_state["minutes_since_open"],
                "is_actionable": session_state["market_session"] == "live_market"
                and not session_state["is_discovery_phase"],
                "reasoning_summary": regime["reasoning_summary"],
            },
            "market_context": {
                "session_state": session_state,
                "primary_indices": primary_indices,
                "sector_indices": sector_indices,
                "index_futures": futures,
                "external_inputs": external_inputs,
            },
        }
        self._save_payload(payload)

        print("\nRegime analysis complete")
        print(f"Market session: {session_state['market_session']}")
        print(f"Market regime: {regime['market_regime']}")
        print(f"Confidence: {regime['confidence']}")
        print(f"Primary indices fetched: {len(primary_indices)}")
        print(f"Sector indices fetched: {len(sector_indices)}")
        print(f"Index futures fetched: {len(futures)}")
        print(f"Saved latest snapshot: {self.config.regime_latest_path.name}")
        print(f"Saved daily snapshot: {self.config.regime_daily_path(self.market_time.market_date_str()).name}")
        return payload
