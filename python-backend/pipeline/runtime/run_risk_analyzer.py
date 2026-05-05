from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.config import PipelineConfig
from pipeline.risk import RiskAnalyzeAgent
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class RiskAnalyzerRunner:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.market_time = MarketTimeService(self.config)
        self.storage = StorageService
        self.dhan = DhanService(self.config, prefer_gateway=False)
        self.agent = RiskAnalyzeAgent()

    def run_cycle(self, force: bool = False) -> Optional[Dict[str, Any]]:
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            print("AI trading is disabled. Risk analyzer is idling.")
            return None

        market_date = self.market_time.market_date_str()
        stock_payload = self._load_required_snapshot(
            self.config.stock_analyzer_daily_path(market_date),
            self.config.stock_analyzer_latest_path,
            "Stock analyzer",
        )
        regime_payload = self._load_required_snapshot(
            self.config.regime_daily_path(market_date),
            self.config.regime_latest_path,
            "Regime",
        )

        stock_reports = list(stock_payload.get("reports") or [])
        if not stock_reports:
            raise RuntimeError("risk_analyzer_no_stock_reports")

        account_context = self._build_account_context()
        risk_packet = self._build_risk_packet(
            market_date=market_date,
            stock_payload=stock_payload,
            regime_payload=regime_payload,
            account_context=account_context,
        )

        existing = self.storage.load_snapshot(self.config.risk_analyzer_latest_path)
        if not force and not self._should_refresh(existing, risk_packet):
            print("Risk analyzer report is still fresh.")
            return existing

        chart_paths = self._collect_chart_paths(stock_reports)
        report_text = self.agent.analyze(risk_packet, chart_paths)
        decision = self._parse_decision_report(report_text)

        selected_report = self._match_selected_report(stock_reports, decision)
        payload = {
            "stage": "risk_analyzer",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "market_date": market_date,
                "status": "completed",
                "selected_symbol": decision.get("selected_symbol"),
                "selected_display_name": decision.get("selected_display_name"),
                "selected_security_id": decision.get("selected_security_id"),
                "action": decision.get("action"),
                "trade_side": decision.get("trade_side"),
                "conviction": decision.get("conviction"),
                "source_snapshots": risk_packet["summary"]["source_snapshots"],
                "chart_count": len(chart_paths),
            },
            "risk_packet": risk_packet,
            "decision": decision,
            "report_text": report_text,
            "selected_report": selected_report,
        }
        self._save_payload(payload)
        print(
            f"Saved risk analyzer snapshot. Decision: {decision.get('action')} {decision.get('selected_display_name') or decision.get('selected_symbol')}."
        )
        return payload

    def _load_required_snapshot(self, daily_path, latest_path, label: str) -> Dict[str, Any]:
        payload = self.storage.load_snapshot(daily_path)
        if payload:
            return payload
        payload = self.storage.load_snapshot(latest_path)
        if payload:
            return payload
        raise FileNotFoundError(f"{label} snapshot not found for risk analyzer.")

    def _build_account_context(self) -> Dict[str, Any]:
        holdings = self.dhan.fetch_holdings()
        positions = self.dhan.fetch_positions()
        fund_limits = self.dhan.fetch_fund_limits()

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

    def _build_risk_packet(
        self,
        market_date: str,
        stock_payload: Dict[str, Any],
        regime_payload: Dict[str, Any],
        account_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        stock_reports = list(stock_payload.get("reports") or [])
        compact_reports: List[Dict[str, Any]] = []
        for report in stock_reports:
            candidate = report.get("candidate") or {}
            analysis = report.get("analysis") or {}
            compact_reports.append(
                {
                    "rank": report.get("rank"),
                    "security_id": candidate.get("security_id"),
                    "symbol": candidate.get("symbol"),
                    "display_name": candidate.get("display_name"),
                    "candidate_source": candidate.get("candidate_source"),
                    "stock": candidate.get("stock"),
                    "stage2": candidate.get("stage2"),
                    "monitor": candidate.get("monitor"),
                    "analysis_report": analysis,
                    "chart_artifacts": candidate.get("chart_artifacts"),
                }
            )

        return {
            "market_date": market_date,
            "summary": {
                "stock_report_count": len(stock_reports),
                "chart_count": sum(
                    int((report.get("candidate") or {}).get("chart_artifacts", {}).get("chart_count", 0))
                    for report in stock_reports
                ),
                "source_snapshots": {
                    "stock_analyzer_generated_at_utc": stock_payload.get("generated_at_utc"),
                    "regime_generated_at_utc": regime_payload.get("generated_at_utc"),
                },
            },
            "market_context": self._build_market_context(regime_payload),
            "account_context": account_context,
            "stock_reports": compact_reports,
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

    def _collect_chart_paths(self, stock_reports: List[Dict[str, Any]]) -> List[str]:
        chart_paths: List[str] = []
        for report in stock_reports:
            charts = (report.get("candidate") or {}).get("chart_artifacts", {}).get("charts", {})
            for timeframe in ("5m", "15m"):
                path = (charts.get(timeframe) or {}).get("path")
                if path:
                    chart_paths.append(str(path))
        return chart_paths

    def _match_selected_report(self, stock_reports: List[Dict[str, Any]], analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        selected_security_id = int(analysis.get("selected_security_id") or 0)
        for report in stock_reports:
            candidate = report.get("candidate") or {}
            if int(candidate.get("security_id") or 0) == selected_security_id:
                return report
        return None

    def _parse_decision_report(self, report_text: str) -> Dict[str, Any]:
        selected_symbol = self._extract_header_value(report_text, "Selected Symbol", default="NONE")
        selected_display_name = self._extract_header_value(report_text, "Selected Display Name", default="NONE")
        selected_security_id_raw = self._extract_header_value(report_text, "Selected Security ID", default="0")
        action_raw = self._extract_header_value(report_text, "Decision", default="AVOID")
        trade_side_raw = self._extract_header_value(report_text, "Trade Side", default="AVOID")
        conviction_raw = self._extract_header_value(report_text, "Conviction", default="0.0")

        try:
            selected_security_id = int(re.findall(r"-?\d+", selected_security_id_raw)[0])
        except Exception:
            selected_security_id = 0

        try:
            conviction = float(re.findall(r"-?\d+(?:\.\d+)?", conviction_raw)[0])
        except Exception:
            conviction = 0.0

        action = action_raw.strip().lower()
        if action not in {"trade", "avoid"}:
            action = "avoid"

        trade_side = trade_side_raw.strip().lower()
        if trade_side not in {"long", "short", "avoid"}:
            trade_side = "avoid"

        return {
            "selected_symbol": selected_symbol.strip(),
            "selected_display_name": selected_display_name.strip(),
            "selected_security_id": selected_security_id,
            "action": action,
            "trade_side": trade_side,
            "conviction": max(0.0, min(1.0, conviction)),
        }

    def _extract_header_value(self, report_text: str, header: str, default: str = "") -> str:
        next_headers = [
            "Decision",
            "Selected Symbol",
            "Selected Display Name",
            "Selected Security ID",
            "Trade Side",
            "Conviction",
        ]
        alternatives = "|".join(re.escape(item) for item in next_headers)
        pattern = rf"(?is){re.escape(header)}\s*:\s*(.+?)(?=\s*(?:{alternatives})\s*:|\Z)"
        match = re.search(pattern, report_text)
        if not match:
            return default
        return " ".join(match.group(1).strip().split())

    def _should_refresh(self, existing: Optional[Dict[str, Any]], risk_packet: Dict[str, Any]) -> bool:
        if not existing:
            return True

        summary = existing.get("summary") or {}
        if summary.get("market_date") != risk_packet.get("market_date"):
            return True

        existing_sources = summary.get("source_snapshots") or {}
        if existing_sources != risk_packet["summary"].get("source_snapshots"):
            return True

        generated_at = existing.get("generated_at_utc")
        if not generated_at:
            return True
        try:
            generated_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        except ValueError:
            return True
        age_seconds = (datetime.now(timezone.utc) - generated_dt).total_seconds()
        return age_seconds >= self.config.risk_analyzer_report_refresh_seconds

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        self.storage.save_snapshot(self.config.risk_analyzer_latest_path, payload)
        self.storage.save_snapshot(
            self.config.risk_analyzer_daily_path(self.market_time.market_date_str()),
            payload,
        )


def main() -> None:
    config = PipelineConfig()
    runner = RiskAnalyzerRunner(config)

    print("=" * 60)
    print("RISK ANALYZER")
    print("=" * 60)
    print(f"Loop interval: {config.risk_analyzer_loop_interval_seconds} seconds")

    while True:
        try:
            runner.run_cycle()
        except Exception as exc:  # pragma: no cover - runtime safety
            print(f"Risk analyzer cycle error: {type(exc).__name__}: {exc}")
        print(
            f"Sleeping for {config.risk_analyzer_loop_interval_seconds} seconds before next risk analyzer cycle..."
        )
        time.sleep(config.risk_analyzer_loop_interval_seconds)


if __name__ == "__main__":
    main()
