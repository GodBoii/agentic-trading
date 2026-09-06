from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from pipeline.analyzer import StockAnalyzerAgent
from pipeline.config import PipelineConfig
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.order_placement_gate import OrderPlacementStateService
from pipeline.services.charting_service import CandlestickChartService
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.signal_data_cache import SignalDataCacheService
from pipeline.services.storage_service import StorageService


class MultiStockAnalyzerRunner:
    def __init__(self, config: Optional[PipelineConfig] = None, initialize_agent: bool = True) -> None:
        self.config = config or PipelineConfig()
        self.market_time = MarketTimeService(self.config)
        self.storage = StorageService
        self.dhan = DhanService(self.config)
        self.signal_cache = SignalDataCacheService(self.config, self.dhan, self.market_time)
        self.charting = CandlestickChartService(
            self.config.market_timezone,
            market_open=(self.config.market_open_hour, self.config.market_open_minute),
            market_close=(self.config.market_close_hour, self.config.market_close_minute),
        )
        self.agent = StockAnalyzerAgent() if initialize_agent else None

    def run_cycle(
        self,
        force: bool = False,
        trade_config: Optional[Dict[str, Any]] = None,
        use_regime_analysis: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        order_state_path = getattr(self.config, "order_placement_state_path", None)
        if order_state_path is not None and not OrderPlacementStateService.is_allowed(order_state_path):
            print("Dhan order placement is blocked. Stock analyzer is idling.")
            return None
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            print("AI trading is disabled. Stock analyzer is idling.")
            return None

        regime_enabled = self._resolve_regime_gate(trade_config, use_regime_analysis)
        market_date = self.market_time.market_date_str()
        stage2_payload = self._load_required_snapshot(
            self.config.stage2_daily_path(market_date),
            self.config.stage2_latest_path,
            "Stage 2",
        )
        regime_payload = None
        if regime_enabled:
            regime_payload = self._load_required_snapshot(
                self.config.regime_daily_path(market_date),
                self.config.regime_latest_path,
                "Regime",
            )
        monitor_payload = self.storage.load_snapshot(self.config.monitor_daily_path(market_date))
        if not monitor_payload:
            monitor_payload = self.storage.load_snapshot(self.config.monitor_latest_path)

        account_context = self._build_account_context()
        effective_trade_config = self._with_effective_trade_amount(trade_config, account_context)
        selected_candidates, candidate_source = self._select_candidates(
            stage2_payload,
            monitor_payload,
            effective_trade_config,
        )
        if not selected_candidates:
            raise RuntimeError("stock_analyzer_no_candidates_selected")

        candidate_packets = [
            self._build_candidate_packet(
                market_date=market_date,
                candidate_record=candidate_record,
                candidate_source=candidate_source,
                stage2_payload=stage2_payload,
                monitor_payload=monitor_payload,
                regime_payload=regime_payload,
                regime_enabled=regime_enabled,
                account_context=account_context,
            )
            for candidate_record in selected_candidates
        ]

        existing = self.storage.load_snapshot(self.config.stock_analyzer_latest_path)
        if not force and not self._should_refresh(existing, candidate_packets):
            print("Stock analyzer batch is still fresh.")
            return existing

        reports = self._analyze_candidates(candidate_packets)
        generated_utc = datetime.now(timezone.utc)
        generated_market = self.market_time.now()
        payload = {
            "stage": "stock_analyzer",
            "generated_at_utc": generated_utc.isoformat(),
            "generated_at_ist": generated_market.isoformat(),
            "summary": {
                "market_date": market_date,
                "market_timezone": self.config.market_timezone,
                "generated_at_ist": generated_market.isoformat(),
                "candidate_source": candidate_source,
                "status": "completed",
                "selected_count": len(reports),
                "selected_symbols": [report["candidate"]["symbol"] for report in reports],
                "selected_security_ids": [report["candidate"]["security_id"] for report in reports],
                "source_snapshots": reports[0]["candidate"]["source_snapshots"],
                "regime_analysis_enabled": regime_enabled,
                "chart_count": sum(int(report["candidate"]["chart_artifacts"].get("chart_count", 0)) for report in reports),
            },
            "reports": reports,
        }
        self._save_payload(payload)
        print(f"Saved stock analyzer batch snapshot for {len(reports)} stock(s).")
        return payload

    def _load_required_snapshot(self, daily_path: Path, latest_path: Path, label: str) -> Dict[str, Any]:
        payload = self.storage.load_snapshot(daily_path)
        if payload and (
            label != "Stage 2"
            or StorageService.is_stage_snapshot_usable(
                payload,
                self.config.stage2_max_fetch_failure_ratio,
            )
        ):
            return payload
        payload = self.storage.load_snapshot(latest_path)
        if payload and (
            label != "Stage 2"
            or StorageService.is_stage_snapshot_usable(
                payload,
                self.config.stage2_max_fetch_failure_ratio,
            )
        ):
            return payload
        raise FileNotFoundError(f"{label} snapshot not found for stock analyzer.")

    def _resolve_regime_gate(
        self,
        trade_config: Optional[Dict[str, Any]],
        explicit_value: Optional[bool],
    ) -> bool:
        # Deprecated. Ignore legacy request/config values so stale clients
        # cannot put regime output back into a stock-agent packet.
        return False

    def _as_bool(self, value: Any, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return default

    def _select_candidates(
        self,
        stage2_payload: Dict[str, Any],
        monitor_payload: Optional[Dict[str, Any]],
        trade_config: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], str]:
        top_n = max(1, int(self.config.stock_analyzer_top_n))

        stage2_stocks = self._build_stage2_selection_pool(stage2_payload)[:10]

        filtered_stocks = self._filter_by_trade_budget(stage2_stocks, trade_config)
        if filtered_stocks:
            return filtered_stocks[:top_n], "stage2"

        if self._is_manual_mode(trade_config):
            return stage2_stocks[:top_n], "stage2_manual_fallback"

        if len(stage2_stocks) >= top_n:
            return stage2_stocks[:top_n], "stage2"

        near_misses = list(stage2_payload.get("summary", {}).get("near_misses") or [])
        combined: List[Dict[str, Any]] = []
        seen_security_ids: set[int] = set()
        for row in stage2_stocks + near_misses:
            try:
                security_id = int(row.get("security_id"))
            except Exception:
                continue
            if security_id in seen_security_ids:
                continue
            seen_security_ids.add(security_id)
            combined.append(row)
            if len(combined) >= top_n:
                break

        if not combined:
            raise RuntimeError("stock_analyzer_no_stage2_candidates")
        return combined, "stage2_fallback"

    def _with_effective_trade_amount(
        self,
        trade_config: Optional[Dict[str, Any]],
        account_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not trade_config:
            return trade_config
        copied = dict(trade_config)
        trade_mode = str(copied.get("trade_mode") or "auto").lower()
        if trade_mode == "auto" and not copied.get("trade_amount"):
            fund_data = (account_context.get("funds") or {}).get("data") or {}
            available_balance = (
                fund_data.get("availabelBalance")
                or fund_data.get("availableBalance")
                or fund_data.get("sodLimit")
            )
            if available_balance:
                copied["trade_amount"] = float(available_balance)
        return copied

    def _build_stage2_selection_pool(self, stage2_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        passed = self._sort_by_stage2_score(list(stage2_payload.get("stocks") or []))
        near_misses = list((stage2_payload.get("summary") or {}).get("near_misses") or [])
        stage1_lookup = self._load_stage1_lookup()

        combined: List[Dict[str, Any]] = []
        seen_security_ids: set[int] = set()
        for row in passed + near_misses:
            try:
                security_id = int(row.get("security_id"))
            except Exception:
                continue
            if security_id in seen_security_ids:
                continue
            seen_security_ids.add(security_id)
            enriched = dict(row)
            stage1_row = stage1_lookup.get(security_id, {})
            for key in (
                "price",
                "adv_20_cr",
                "atr_percent",
                "avg_volume_20",
                "previous_session",
                "static_tradability",
                "derivatives",
                "instrument",
                "symbol",
                "display_name",
            ):
                if enriched.get(key) in (None, "") and stage1_row.get(key) not in (None, ""):
                    enriched[key] = stage1_row.get(key)
            combined.append(enriched)
        return combined

    def _load_stage1_lookup(self) -> Dict[int, Dict[str, Any]]:
        payload = self.storage.load_snapshot(self.config.stage1_daily_path(self.market_time.market_date_str()))
        if not payload:
            payload = self.storage.load_snapshot(self.config.stage1_latest_path)
        lookup: Dict[int, Dict[str, Any]] = {}
        for row in (payload or {}).get("stocks") or []:
            try:
                lookup[int(row.get("security_id"))] = row
            except Exception:
                continue
        return lookup

    def _is_manual_mode(self, trade_config: Optional[Dict[str, Any]]) -> bool:
        if not trade_config:
            return False
        return str(trade_config.get("trade_mode") or "auto").lower() == "manual"

    def _sort_by_stage2_score(self, stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        copied = list(stocks)
        copied.sort(
            key=lambda s: float(
                s.get("selection_score")
                or s.get("stage2_selection_score")
                or s.get("stage2_score")
                or s.get("score")
                or 0
            ),
            reverse=True,
        )
        return copied

    def _filter_by_trade_budget(
        self,
        stocks: List[Dict[str, Any]],
        trade_config: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter the Stage 2 top ten by manual amount before analyzing top candidates."""
        if not trade_config:
            return []
        trade_mode = str(trade_config.get("trade_mode") or "auto").lower()
        trade_amount = trade_config.get("trade_amount")

        if trade_mode == "manual" and trade_amount:
            budget = float(trade_amount)
        elif trade_mode == "auto":
            return []
        else:
            return []

        affordable = [s for s in stocks if float(s.get("price") or 0) <= budget and float(s.get("price") or 0) > 0]
        return self._sort_by_stage2_score(affordable)

    def _build_account_context(self, dhan: Optional[DhanService] = None) -> Dict[str, Any]:
        account = dhan or self.dhan
        holdings = account.fetch_holdings()
        positions = account.fetch_positions()
        fund_limits = account.fetch_fund_limits()

        holdings_rows = holdings.get("data") if isinstance(holdings.get("data"), list) else []
        positions_rows = positions.get("data") if isinstance(positions.get("data"), list) else []
        raw_fund_data = fund_limits.get("data") if isinstance(fund_limits.get("data"), dict) else {}
        fund_data = raw_fund_data.get("data") if isinstance(raw_fund_data.get("data"), dict) else raw_fund_data

        return {
            "holdings": {
                "status": holdings.get("status"),
                "count": len(holdings_rows),
                "items": holdings_rows,
            },
            "positions": {
                "status": positions.get("status"),
                "count": len(positions_rows),
                "open_intraday_count": sum(
                    1
                    for row in positions_rows
                    if str(row.get("productType", "")).upper() == "INTRADAY" and float(row.get("netQty") or 0) != 0.0
                ),
                "items": positions_rows,
            },
            "funds": {
                "status": fund_limits.get("status"),
                "data": fund_data,
            },
            "fetch_status": {
                "holdings": holdings.get("status"),
                "positions": positions.get("status"),
                "funds": fund_limits.get("status"),
            },
        }

    def _analyze_candidates(self, candidate_packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        max_workers = min(len(candidate_packets), max(1, int(self.config.stock_analyzer_top_n)))
        reports: Dict[int, Dict[str, Any]] = {}
        failures: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self._analyze_single_candidate, index, packet): index
                for index, packet in enumerate(candidate_packets)
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    reports[index] = future.result()
                except Exception as exc:
                    packet = candidate_packets[index]
                    failures.append(
                        {
                            "rank": index + 1,
                            "security_id": packet.get("security_id"),
                            "symbol": packet.get("symbol"),
                            "display_name": packet.get("display_name"),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

        if failures:
            print(f"Stock analyzer skipped {len(failures)} candidate(s): {failures}")

        ordered_reports = [reports[index] for index in sorted(reports.keys())]
        if ordered_reports:
            return ordered_reports

        auth_failures = [item for item in failures if "stock_analyzer_auth_invalid::" in str(item.get("error"))]
        if auth_failures:
            raise RuntimeError(auth_failures[0]["error"])

        raise RuntimeError(f"stock_analyzer_all_candidates_failed::{failures}")

    def _analyze_single_candidate(self, index: int, candidate_packet: Dict[str, Any]) -> Dict[str, Any]:
        intraday_resp = self.dhan.fetch_intraday_history(
            int(candidate_packet["security_id"]),
            days=5,
            interval=1,
            exchange_segment=str(candidate_packet.get("exchange_segment") or "").upper(),
            instrument_candidates=[candidate_packet.get("instrument"), "EQUITY"],
        )
        if not intraday_resp or str(intraday_resp.get("status", "")).lower() != "success":
            remarks = intraday_resp.get("remarks") if isinstance(intraday_resp, dict) else None
            if self.dhan.is_auth_invalid(intraday_resp):
                raise RuntimeError(f"stock_analyzer_auth_invalid::{remarks}")
            raise RuntimeError(
                f"stock_analyzer_intraday_history_failed::{candidate_packet['security_id']}::{remarks}"
            )

        intraday_frame = self.dhan.intraday_response_to_df(intraday_resp)
        artifacts_dir = (
            self.config.stock_analyzer_artifacts_dir
            / candidate_packet["market_date"]
            / self._slugify(candidate_packet["display_name"])
        )
        chart_bundle = self.charting.build_intraday_chart_set(
            frame=intraday_frame,
            display_name=candidate_packet["display_name"],
            market_date=candidate_packet["market_date"],
            output_dir=artifacts_dir,
            daily_frame=self._fetch_daily_chart_history(candidate_packet),
        )
        candidate_packet["chart_artifacts"] = chart_bundle

        # Use all generated chart paths (current day + previous day, multiple timeframes)
        chart_paths = chart_bundle.get("chart_paths_ordered", [])
        if not chart_paths:
            # Fallback: collect from charts dict
            chart_paths = [info["path"] for info in chart_bundle.get("charts", {}).values()]
        print(
            f"[rank {index + 1}] Analyzing {candidate_packet['display_name']} using {len(chart_paths)} chart images..."
        )
        analysis = self.agent.analyze(candidate_packet, chart_paths)
        return {
            "rank": index + 1,
            "candidate": candidate_packet,
            "analysis": analysis,
        }

    def _fetch_daily_chart_history(self, candidate_packet: Dict[str, Any]) -> pd.DataFrame:
        """Fetch a full year of daily context through the shared rate-limited gateway.

        Stage 1 only requests 60 calendar days, so its cache is too short for this
        chart. A separate daily endpoint request avoids synthesizing daily bars
        from a partial intraday history window.
        """
        security_id = int(candidate_packet["security_id"])
        response = self.dhan.fetch_daily_history(
            security_id,
            days=400,
            exchange_segment=str(candidate_packet.get("exchange_segment") or "").upper(),
            instrument_candidates=[candidate_packet.get("instrument"), "EQUITY"],
        )
        if not response or str(response.get("status") or "").lower() != "success":
            if self.dhan.is_auth_invalid(response):
                raise RuntimeError(f"stock_agent_auth_invalid::daily_history::{security_id}")
            raise RuntimeError(f"stock_daily_history_failed::{security_id}")
        frame = self.dhan.daily_response_to_df(response)
        if frame.empty:
            raise RuntimeError(f"stock_daily_history_empty::{security_id}")
        return frame

    def _build_candidate_packet(
        self,
        market_date: str,
        candidate_record: Dict[str, Any],
        candidate_source: str,
        stage2_payload: Dict[str, Any],
        monitor_payload: Optional[Dict[str, Any]],
        regime_payload: Optional[Dict[str, Any]],
        regime_enabled: bool,
        account_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        security_id = int(candidate_record["security_id"])
        stage2_record = self._find_stock(stage2_payload, security_id)
        monitor_record = self._find_stock(monitor_payload, security_id) if monitor_payload else None
        regime_report = self._build_regime_report(regime_payload) if regime_enabled and regime_payload else None
        timing_context = self._build_timing_context(stage2_payload, monitor_payload, regime_payload)
        source_snapshots = {
            "stage2_generated_at_utc": stage2_payload.get("generated_at_utc"),
            "stage2_generated_at_ist": self._to_market_iso(stage2_payload.get("generated_at_utc")),
            "monitor_generated_at_utc": monitor_payload.get("generated_at_utc") if monitor_payload else None,
            "monitor_generated_at_ist": self._to_market_iso(monitor_payload.get("generated_at_utc")) if monitor_payload else None,
            "regime_analysis_enabled": regime_enabled,
        }
        if regime_enabled and regime_payload:
            source_snapshots.update(
                {
                    "regime_generated_at_utc": regime_payload.get("generated_at_utc"),
                    "regime_generated_at_ist": self._to_market_iso(regime_payload.get("generated_at_utc")),
                }
            )

        packet = {
            "market_date": market_date,
            "timing_context": timing_context,
            "candidate_source": candidate_source,
            "regime_analysis_enabled": regime_enabled,
            "security_id": security_id,
            "isin": candidate_record.get("isin"),
            "exchange_segment": candidate_record.get("exchange_segment"),
            "symbol": candidate_record.get("symbol"),
            "display_name": candidate_record.get("display_name"),
            "instrument": candidate_record.get("instrument"),
            "stock": {
                "price": candidate_record.get("price"),
                "adv_20_cr": stage2_record.get("adv_20_cr") if stage2_record else candidate_record.get("adv_20_cr"),
                "atr_percent": stage2_record.get("atr_percent") if stage2_record else candidate_record.get("atr_percent"),
                "avg_volume_20": stage2_record.get("avg_volume_20") if stage2_record else candidate_record.get("avg_volume_20"),
                "previous_session": stage2_record.get("previous_session") if stage2_record else candidate_record.get("previous_session"),
                "static_tradability": stage2_record.get("static_tradability") if stage2_record else candidate_record.get("static_tradability"),
                "derivatives": stage2_record.get("derivatives") if stage2_record else candidate_record.get("derivatives"),
                "exchange_segment": candidate_record.get("exchange_segment"),
            },
            "stage2": {
                "score": stage2_record.get("stage2_score") if stage2_record else candidate_record.get("stage2_score"),
                "selection_score": stage2_record.get("selection_score") if stage2_record else candidate_record.get("selection_score"),
                "live_liquidity": stage2_record.get("live_liquidity") if stage2_record else candidate_record.get("live_liquidity"),
                "data_quality": stage2_record.get("data_quality") if stage2_record else candidate_record.get("data_quality"),
                "live_quote": stage2_record.get("live_quote") if stage2_record else candidate_record.get("live_quote"),
                "time_of_day_rvol": stage2_record.get("time_of_day_rvol") if stage2_record else candidate_record.get("time_of_day_rvol"),
                "price_vs_vwap_percent": stage2_record.get("price_vs_vwap_percent") if stage2_record else candidate_record.get("price_vs_vwap_percent"),
                "opening_range_breakout_percent": (
                    stage2_record.get("opening_range_breakout_percent") if stage2_record else candidate_record.get("opening_range_breakout_percent")
                ),
                "volume_acceleration_ratio": (
                    stage2_record.get("volume_acceleration_ratio") if stage2_record else candidate_record.get("volume_acceleration_ratio")
                ),
                "stage2_reason": stage2_record.get("stage2_reason") if stage2_record else candidate_record.get("stage2_reason"),
            },
            "monitor": {
                "passed": bool(monitor_record),
                "spread_percent": monitor_record.get("spread_percent") if monitor_record else None,
                "ticks_last_10min": monitor_record.get("ticks_last_10min") if monitor_record else None,
                "time_of_day_rvol": monitor_record.get("time_of_day_rvol") if monitor_record else None,
                "intraday_value_cr": monitor_record.get("intraday_value_cr") if monitor_record else None,
            },
            "account_context": account_context,
            "source_snapshots": source_snapshots,
            "chart_artifacts": {},
        }
        if regime_report:
            packet["regime_report"] = regime_report
        return packet

    def _build_timing_context(
        self,
        stage2_payload: Dict[str, Any],
        monitor_payload: Optional[Dict[str, Any]],
        regime_payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        now_market = self.market_time.now()
        open_dt = now_market.replace(
            hour=self.config.market_open_hour,
            minute=self.config.market_open_minute,
            second=0,
            microsecond=0,
        )
        close_dt = now_market.replace(
            hour=self.config.market_close_hour,
            minute=self.config.market_close_minute,
            second=0,
            microsecond=0,
        )
        source_snapshot_times = {
            "stage2_generated_at_utc": stage2_payload.get("generated_at_utc"),
            "stage2_generated_at_ist": self._to_market_iso(stage2_payload.get("generated_at_utc")),
            "monitor_generated_at_utc": monitor_payload.get("generated_at_utc") if monitor_payload else None,
            "monitor_generated_at_ist": self._to_market_iso(monitor_payload.get("generated_at_utc")) if monitor_payload else None,
        }
        source_snapshot_ages_seconds = {
            "stage2": self._age_seconds(stage2_payload.get("generated_at_utc"), now_utc),
            "monitor": self._age_seconds(monitor_payload.get("generated_at_utc"), now_utc) if monitor_payload else None,
        }
        if regime_payload:
            source_snapshot_times.update(
                {
                    "regime_generated_at_utc": regime_payload.get("generated_at_utc"),
                    "regime_generated_at_ist": self._to_market_iso(regime_payload.get("generated_at_utc")),
                }
            )
            source_snapshot_ages_seconds["regime"] = self._age_seconds(regime_payload.get("generated_at_utc"), now_utc)

        return {
            "analysis_started_at_utc": now_utc.isoformat(),
            "analysis_started_at_ist": now_market.isoformat(),
            "current_market_time_ist": now_market.isoformat(),
            "market_timezone": self.config.market_timezone,
            "market_session": {
                "open_time_ist": open_dt.isoformat(),
                "close_time_ist": close_dt.isoformat(),
                "regular_session": "09:15-15:30 IST",
                "is_open_now": bool(open_dt <= now_market <= close_dt),
                "minutes_since_open": max(0, int((now_market - open_dt).total_seconds() // 60)),
                "minutes_to_close": max(0, int((close_dt - now_market).total_seconds() // 60)),
            },
            "source_snapshot_times": source_snapshot_times,
            "source_snapshot_ages_seconds": source_snapshot_ages_seconds,
        }

    def _build_regime_report(self, regime_payload: Dict[str, Any]) -> Optional[str]:
        regime = regime_payload.get("regime") or {}
        report = str(regime.get("human_readable_report") or "").strip()
        if not report:
            return None
        lowered = report.lower()
        if "unavailable" in lowered or "fallback" in lowered or "invalid output" in lowered:
            return None
        return report

    def _age_seconds(self, value: Any, now: Optional[datetime] = None) -> Optional[float]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return round(((now or datetime.now(timezone.utc)) - dt.astimezone(timezone.utc)).total_seconds(), 3)
        except Exception:
            return None

    def _to_market_iso(self, value: Any) -> Optional[str]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(self.market_time.tz).isoformat()
        except Exception:
            return None

    def _find_stock(self, payload: Optional[Dict[str, Any]], security_id: int) -> Dict[str, Any]:
        if not payload:
            return {}
        for row in payload.get("stocks") or []:
            try:
                if int(row.get("security_id")) == security_id:
                    return row
            except Exception:
                continue
        return {}

    def _should_refresh(self, existing: Optional[Dict[str, Any]], candidate_packets: List[Dict[str, Any]]) -> bool:
        if not existing:
            return True

        summary = existing.get("summary") or {}
        if summary.get("market_date") != candidate_packets[0].get("market_date"):
            return True

        expected_ids = [int(packet["security_id"]) for packet in candidate_packets]
        actual_ids = [int(item) for item in summary.get("selected_security_ids") or []]
        if actual_ids != expected_ids:
            return True

        existing_sources = summary.get("source_snapshots") or {}
        if existing_sources != candidate_packets[0].get("source_snapshots"):
            return True

        generated_at = existing.get("generated_at_utc")
        if not generated_at:
            return True
        try:
            generated_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        except ValueError:
            return True
        age_seconds = (datetime.now(timezone.utc) - generated_dt).total_seconds()
        return age_seconds >= self.config.stock_analyzer_report_refresh_seconds

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        self.storage.save_snapshot(self.config.stock_analyzer_latest_path, payload)
        self.storage.save_snapshot(
            self.config.stock_analyzer_daily_path(self.market_time.market_date_str()),
            payload,
        )

    def _slugify(self, value: str) -> str:
        return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "stock"


def main() -> None:
    config = PipelineConfig()
    runner = MultiStockAnalyzerRunner(config)

    print("=" * 60)
    print("STOCK ANALYZER")
    print("=" * 60)
    print(f"Loop interval: {config.stock_analyzer_loop_interval_seconds} seconds")
    print(f"Top N candidates: {config.stock_analyzer_top_n}")

    while True:
        try:
            runner.run_cycle()
        except Exception as exc:  # pragma: no cover - runtime safety
            print(f"Stock analyzer cycle error: {type(exc).__name__}: {exc}")
        print(
            f"Sleeping for {config.stock_analyzer_loop_interval_seconds} seconds before next analyzer cycle..."
        )
        time.sleep(config.stock_analyzer_loop_interval_seconds)


if __name__ == "__main__":
    main()
