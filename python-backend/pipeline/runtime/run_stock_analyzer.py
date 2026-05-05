from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.analyzer import StockAnalyzerAgent
from pipeline.config import PipelineConfig
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.charting_service import CandlestickChartService
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class MultiStockAnalyzerRunner:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.market_time = MarketTimeService(self.config)
        self.storage = StorageService
        self.dhan = DhanService(self.config)
        self.charting = CandlestickChartService(self.config.market_timezone)
        self.agent = StockAnalyzerAgent()

    def run_cycle(self, force: bool = False) -> Optional[Dict[str, Any]]:
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            print("AI trading is disabled. Stock analyzer is idling.")
            return None

        market_date = self.market_time.market_date_str()
        stage2_payload = self._load_required_snapshot(
            self.config.stage2_daily_path(market_date),
            self.config.stage2_latest_path,
            "Stage 2",
        )
        regime_payload = self._load_required_snapshot(
            self.config.regime_daily_path(market_date),
            self.config.regime_latest_path,
            "Regime",
        )
        monitor_payload = self.storage.load_snapshot(self.config.monitor_daily_path(market_date))
        if not monitor_payload:
            monitor_payload = self.storage.load_snapshot(self.config.monitor_latest_path)

        selected_candidates, candidate_source = self._select_candidates(stage2_payload, monitor_payload)
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
            )
            for candidate_record in selected_candidates
        ]

        existing = self.storage.load_snapshot(self.config.stock_analyzer_latest_path)
        if not force and not self._should_refresh(existing, candidate_packets):
            print("Stock analyzer batch is still fresh.")
            return existing

        reports = self._analyze_candidates(candidate_packets)
        payload = {
            "stage": "stock_analyzer",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "market_date": market_date,
                "candidate_source": candidate_source,
                "status": "completed",
                "selected_count": len(reports),
                "selected_symbols": [report["candidate"]["symbol"] for report in reports],
                "selected_security_ids": [report["candidate"]["security_id"] for report in reports],
                "source_snapshots": reports[0]["candidate"]["source_snapshots"],
                "chart_count": sum(int(report["candidate"]["chart_artifacts"].get("chart_count", 0)) for report in reports),
            },
            "reports": reports,
        }
        self._save_payload(payload)
        print(f"Saved stock analyzer batch snapshot for {len(reports)} stock(s).")
        return payload

    def _load_required_snapshot(self, daily_path: Path, latest_path: Path, label: str) -> Dict[str, Any]:
        payload = self.storage.load_snapshot(daily_path)
        if payload:
            return payload
        payload = self.storage.load_snapshot(latest_path)
        if payload:
            return payload
        raise FileNotFoundError(f"{label} snapshot not found for stock analyzer.")

    def _select_candidates(
        self,
        stage2_payload: Dict[str, Any],
        monitor_payload: Optional[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], str]:
        top_n = max(1, int(self.config.stock_analyzer_top_n))

        monitor_stocks = monitor_payload.get("stocks") if monitor_payload else None
        if isinstance(monitor_stocks, list) and monitor_stocks:
            return monitor_stocks[:top_n], "monitor"

        stage2_stocks = list(stage2_payload.get("stocks") or [])
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
            exchange_segment="BSE_EQ",
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
        )
        candidate_packet["chart_artifacts"] = chart_bundle

        chart_paths = [
            chart_bundle["charts"]["5m"]["path"],
            chart_bundle["charts"]["15m"]["path"],
        ]
        print(
            f"[rank {index + 1}] Analyzing {candidate_packet['display_name']} using {len(chart_paths)} chart images..."
        )
        analysis = self.agent.analyze(candidate_packet, chart_paths)
        return {
            "rank": index + 1,
            "candidate": candidate_packet,
            "analysis": analysis,
        }

    def _build_candidate_packet(
        self,
        market_date: str,
        candidate_record: Dict[str, Any],
        candidate_source: str,
        stage2_payload: Dict[str, Any],
        monitor_payload: Optional[Dict[str, Any]],
        regime_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        security_id = int(candidate_record["security_id"])
        stage2_record = self._find_stock(stage2_payload, security_id)
        monitor_record = self._find_stock(monitor_payload, security_id) if monitor_payload else None
        market_context = self._build_market_context(regime_payload)

        return {
            "market_date": market_date,
            "candidate_source": candidate_source,
            "security_id": security_id,
            "symbol": candidate_record.get("symbol"),
            "display_name": candidate_record.get("display_name"),
            "instrument": candidate_record.get("instrument"),
            "stock": {
                "price": candidate_record.get("price"),
                "adv_20_cr": stage2_record.get("adv_20_cr") if stage2_record else candidate_record.get("adv_20_cr"),
                "atr_percent": stage2_record.get("atr_percent") if stage2_record else candidate_record.get("atr_percent"),
            },
            "stage2": {
                "score": stage2_record.get("stage2_score") if stage2_record else candidate_record.get("stage2_score"),
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
            "market_context": market_context,
            "source_snapshots": {
                "stage2_generated_at_utc": stage2_payload.get("generated_at_utc"),
                "monitor_generated_at_utc": monitor_payload.get("generated_at_utc") if monitor_payload else None,
                "regime_generated_at_utc": regime_payload.get("generated_at_utc"),
            },
            "chart_artifacts": {},
        }

    def _build_market_context(self, regime_payload: Dict[str, Any]) -> Dict[str, Any]:
        regime = regime_payload.get("regime") or {}
        return {
            "market_regime": regime.get("market_regime"),
            "confidence": regime.get("confidence"),
            "status": regime.get("status"),
            "minutes_since_open": regime.get("minutes_since_open"),
            "is_actionable": regime.get("is_actionable"),
            "reasoning_summary": regime.get("reasoning_summary"),
            "diagnostics": regime.get("diagnostics", {}),
            "news_analysis": regime.get("news_analysis", {}),
            "generated_at_utc": regime_payload.get("generated_at_utc"),
        }

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
