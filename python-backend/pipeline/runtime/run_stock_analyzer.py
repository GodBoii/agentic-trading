from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.analyzer import StockAnalyzerAgent
from pipeline.config import PipelineConfig
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.charting_service import CandlestickChartService
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class SingleStockAnalyzerRunner:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.market_time = MarketTimeService(self.config)
        self.storage = StorageService
        self.dhan = DhanService(self.config)
        self.charting = CandlestickChartService(self.config.market_timezone)
        self.agent = StockAnalyzerAgent()

    def run_cycle(self) -> Optional[Dict[str, Any]]:
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

        candidate_record, candidate_source = self._select_candidate(stage2_payload, monitor_payload)
        candidate_packet = self._build_candidate_packet(
            market_date=market_date,
            candidate_record=candidate_record,
            candidate_source=candidate_source,
            stage2_payload=stage2_payload,
            monitor_payload=monitor_payload,
            regime_payload=regime_payload,
        )

        existing = self.storage.load_snapshot(self.config.stock_analyzer_latest_path)
        if not self._should_refresh(existing, candidate_packet):
            print(
                f"Stock analyzer report is still fresh for {candidate_packet['symbol']}."
            )
            return existing

        intraday_resp = self.dhan.fetch_intraday_history(
            int(candidate_record["security_id"]),
            days=5,
            interval=1,
            exchange_segment="BSE_EQ",
            instrument_candidates=[candidate_record.get("instrument"), "EQUITY"],
        )
        if not intraday_resp or str(intraday_resp.get("status", "")).lower() != "success":
            raise RuntimeError("stock_analyzer_intraday_history_failed")

        intraday_frame = self.dhan.intraday_response_to_df(intraday_resp)
        artifacts_dir = (
            self.config.stock_analyzer_artifacts_dir
            / market_date
            / self._slugify(candidate_packet["display_name"])
        )
        chart_bundle = self.charting.build_intraday_chart_set(
            frame=intraday_frame,
            display_name=candidate_packet["display_name"],
            market_date=market_date,
            output_dir=artifacts_dir,
        )
        candidate_packet["chart_artifacts"] = chart_bundle

        chart_paths = [
            chart_bundle["charts"]["5m"]["path"],
            chart_bundle["charts"]["15m"]["path"],
        ]
        print(
            f"Analyzing {candidate_packet['display_name']} using {len(chart_paths)} chart images..."
        )
        analysis = self.agent.analyze(candidate_packet, chart_paths)

        payload = {
            "stage": "stock_analyzer",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "market_date": market_date,
                "candidate_source": candidate_source,
                "security_id": candidate_packet["security_id"],
                "symbol": candidate_packet["symbol"],
                "display_name": candidate_packet["display_name"],
                "status": "completed",
                "trade_bias": analysis.get("trade_bias"),
                "confidence": analysis.get("confidence"),
                "source_snapshots": candidate_packet["source_snapshots"],
                "chart_count": chart_bundle.get("chart_count"),
            },
            "candidate": candidate_packet,
            "analysis": analysis,
        }
        self._save_payload(payload)
        print(
            f"Saved stock analyzer snapshot for {candidate_packet['display_name']} ({candidate_packet['symbol']})."
        )
        return payload

    def _load_required_snapshot(self, daily_path: Path, latest_path: Path, label: str) -> Dict[str, Any]:
        payload = self.storage.load_snapshot(daily_path)
        if payload:
            return payload
        payload = self.storage.load_snapshot(latest_path)
        if payload:
            return payload
        raise FileNotFoundError(f"{label} snapshot not found for stock analyzer.")

    def _select_candidate(
        self,
        stage2_payload: Dict[str, Any],
        monitor_payload: Optional[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str]:
        if monitor_payload and isinstance(monitor_payload.get("stocks"), list) and monitor_payload["stocks"]:
            return monitor_payload["stocks"][0], "monitor"

        stage2_stocks = stage2_payload.get("stocks") or []
        if not stage2_stocks:
            raise RuntimeError("stock_analyzer_no_stage2_candidates")
        return stage2_stocks[0], "stage2"

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
        regime = regime_payload.get("regime") or {}

        return {
            "market_date": market_date,
            "candidate_source": candidate_source,
            "security_id": security_id,
            "symbol": candidate_record.get("symbol"),
            "display_name": candidate_record.get("display_name"),
            "stock": {
                "price": candidate_record.get("price"),
                "adv_20_cr": stage2_record.get("adv_20_cr") if stage2_record else candidate_record.get("adv_20_cr"),
                "atr_percent": stage2_record.get("atr_percent") if stage2_record else candidate_record.get("atr_percent"),
            },
            "stage2": {
                "score": stage2_record.get("stage2_score") if stage2_record else None,
                "time_of_day_rvol": stage2_record.get("time_of_day_rvol") if stage2_record else None,
                "price_vs_vwap_percent": stage2_record.get("price_vs_vwap_percent") if stage2_record else None,
                "opening_range_breakout_percent": (
                    stage2_record.get("opening_range_breakout_percent") if stage2_record else None
                ),
                "volume_acceleration_ratio": (
                    stage2_record.get("volume_acceleration_ratio") if stage2_record else None
                ),
            },
            "monitor": {
                "passed": bool(monitor_record),
                "spread_percent": monitor_record.get("spread_percent") if monitor_record else None,
                "ticks_last_10min": monitor_record.get("ticks_last_10min") if monitor_record else None,
                "time_of_day_rvol": monitor_record.get("time_of_day_rvol") if monitor_record else None,
                "intraday_value_cr": monitor_record.get("intraday_value_cr") if monitor_record else None,
            },
            "regime": {
                "market_regime": regime.get("market_regime"),
                "confidence": regime.get("confidence"),
                "trade_permission": regime.get("trade_permission"),
                "preferred_style": regime.get("preferred_style"),
                "long_bias": regime.get("long_bias"),
                "short_bias": regime.get("short_bias"),
                "position_size_multiplier": regime.get("position_size_multiplier"),
                "max_concurrent_positions": regime.get("max_concurrent_positions"),
                "reasoning_summary": regime.get("reasoning_summary"),
            },
            "source_snapshots": {
                "stage2_generated_at_utc": stage2_payload.get("generated_at_utc"),
                "monitor_generated_at_utc": monitor_payload.get("generated_at_utc") if monitor_payload else None,
                "regime_generated_at_utc": regime_payload.get("generated_at_utc"),
            },
            "chart_artifacts": {},
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

    def _should_refresh(self, existing: Optional[Dict[str, Any]], candidate_packet: Dict[str, Any]) -> bool:
        if not existing:
            return True

        summary = existing.get("summary") or {}
        if summary.get("market_date") != candidate_packet.get("market_date"):
            return True
        if int(summary.get("security_id") or 0) != int(candidate_packet.get("security_id") or 0):
            return True

        existing_sources = summary.get("source_snapshots") or {}
        if existing_sources != candidate_packet.get("source_snapshots"):
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
    runner = SingleStockAnalyzerRunner(config)

    print("=" * 60)
    print("STOCK ANALYZER")
    print("=" * 60)
    print(f"Loop interval: {config.stock_analyzer_loop_interval_seconds} seconds")

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
