from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.config import PipelineConfig
from pipeline.execution import ExecutionerAgent
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.dhan_execution_toolkit import DhanExecutionToolkit
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class ExecutionerRunner:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.market_time = MarketTimeService(self.config)
        self.storage = StorageService
        self.dhan = DhanService(self.config, prefer_gateway=False)
        self.toolkit = DhanExecutionToolkit(self.dhan)
        self.agent = ExecutionerAgent(self.toolkit)

    def run_cycle(self) -> Optional[Dict[str, Any]]:
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            print("AI trading is disabled. Executioner is idling.")
            return None

        market_date = self.market_time.market_date_str()
        risk_payload = self._load_required_snapshot(
            self.config.risk_analyzer_daily_path(market_date),
            self.config.risk_analyzer_latest_path,
            "Risk analyzer",
        )
        stock_payload = self._load_required_snapshot(
            self.config.stock_analyzer_daily_path(market_date),
            self.config.stock_analyzer_latest_path,
            "Stock analyzer",
        )

        execution_packet = self._build_execution_packet(market_date, risk_payload, stock_payload)
        if not execution_packet:
            return self._save_no_trade_payload(market_date, risk_payload, "No selected stock from risk analyzer.")

        existing = self.storage.load_snapshot(self.config.executioner_latest_path)
        if not self._should_refresh(existing, execution_packet):
            print("Executioner report is still fresh.")
            return existing

        chart_paths = execution_packet["selected_stock"]["chart_paths"]
        report_text = self.agent.analyze(execution_packet, chart_paths)
        decision = self._parse_execution_report(report_text)

        payload = {
            "stage": "executioner",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "market_date": market_date,
                "status": decision.get("execution_status"),
                "selected_security_id": decision.get("selected_security_id"),
                "selected_display_name": decision.get("selected_display_name"),
                "action": decision.get("action"),
                "trade_side": decision.get("trade_side"),
                "quantity": decision.get("quantity"),
                "order_type": decision.get("order_type"),
                "order_id": decision.get("order_id"),
                "correlation_id": decision.get("correlation_id"),
                "source_snapshots": execution_packet["summary"]["source_snapshots"],
                "chart_count": len(chart_paths),
            },
            "execution_packet": execution_packet,
            "decision": decision,
            "report_text": report_text,
        }
        self._save_payload(payload)
        print(
            f"Saved executioner snapshot. Decision: {decision.get('action')} {decision.get('selected_display_name')} ({decision.get('execution_status')})."
        )
        return payload

    def _build_execution_packet(
        self,
        market_date: str,
        risk_payload: Dict[str, Any],
        stock_payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        risk_packet = risk_payload.get("risk_packet") or {}
        decision = risk_payload.get("decision") or {}
        selected_security_id = int(decision.get("selected_security_id") or 0)
        selected_report = self._resolve_selected_stock_report(
            stock_payload=stock_payload,
            risk_payload=risk_payload,
            decision=decision,
        )

        if not selected_report:
            return None

        selected_stock = self._normalize_selected_stock(selected_report)
        if not selected_stock["chart_paths"]:
            raise RuntimeError("executioner_missing_chart_paths")

        analysis_payload = selected_report.get("analysis_report")
        if analysis_payload is None:
            analysis_payload = selected_report.get("analysis")

        return {
            "market_date": market_date,
            "summary": {
                "source_snapshots": {
                    "risk_analyzer_generated_at_utc": risk_payload.get("generated_at_utc"),
                    "stock_analyzer_generated_at_utc": stock_payload.get("generated_at_utc"),
                    "regime_generated_at_utc": (risk_packet.get("summary") or {}).get("source_snapshots", {}).get(
                        "regime_generated_at_utc"
                    ),
                }
            },
            "selected_stock": selected_stock,
            "stock_analysis": self._normalize_stock_analysis(analysis_payload),
            "risk_decision": decision,
            "risk_report_text": risk_payload.get("report_text"),
            "market_context": risk_packet.get("market_context") or risk_packet.get("regime") or {},
            "account_context": risk_packet.get("account_context") or {},
            "user_profile": self.dhan.fetch_user_profile(),
        }

    def _resolve_selected_stock_report(
        self,
        *,
        stock_payload: Dict[str, Any],
        risk_payload: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        selected_security_id = int(decision.get("selected_security_id") or 0)
        selected_display_name = str(decision.get("selected_display_name") or "").strip()
        selected_symbol = str(decision.get("selected_symbol") or "").strip()

        stock_reports = list(stock_payload.get("reports") or [])
        risk_selected_report = risk_payload.get("selected_report")

        if selected_security_id > 0:
            matched = self._match_stock_report_by_security_id(stock_reports, selected_security_id)
            if matched:
                return matched

        if selected_display_name:
            matched = self._match_stock_report_by_text(stock_reports, selected_display_name)
            if matched:
                return matched

        if selected_symbol:
            matched = self._match_stock_report_by_text(stock_reports, selected_symbol)
            if matched:
                return matched

        if risk_selected_report:
            return risk_selected_report

        return None

    def _match_stock_report_by_security_id(
        self,
        stock_reports: List[Dict[str, Any]],
        selected_security_id: int,
    ) -> Optional[Dict[str, Any]]:
        for report in stock_reports:
            candidate = report.get("candidate") or {}
            try:
                if int(candidate.get("security_id") or 0) == selected_security_id:
                    return report
            except Exception:
                continue
        return None

    def _match_stock_report_by_text(
        self,
        stock_reports: List[Dict[str, Any]],
        text: str,
    ) -> Optional[Dict[str, Any]]:
        needle = self._normalize_text(text)
        if not needle:
            return None

        for report in stock_reports:
            candidate = report.get("candidate") or {}
            haystacks = [
                candidate.get("display_name"),
                candidate.get("symbol"),
            ]
            for haystack in haystacks:
                if self._normalize_text(str(haystack or "")) == needle:
                    return report
        return None

    def _normalize_selected_stock(self, selected_report: Dict[str, Any]) -> Dict[str, Any]:
        candidate = selected_report.get("candidate") or {}
        base = candidate if candidate else selected_report
        chart_artifacts = base.get("chart_artifacts") or selected_report.get("chart_artifacts") or {}
        charts = chart_artifacts.get("charts") or {}
        chart_paths: List[str] = []
        for timeframe in ("5m", "15m"):
            path = (charts.get(timeframe) or {}).get("path")
            if path:
                chart_paths.append(str(path))

        return {
            "rank": selected_report.get("rank"),
            "security_id": int(base.get("security_id") or selected_report.get("security_id") or 0),
            "symbol": base.get("symbol") or selected_report.get("symbol"),
            "display_name": base.get("display_name") or selected_report.get("display_name"),
            "candidate_source": base.get("candidate_source") or selected_report.get("candidate_source"),
            "stock": base.get("stock") or selected_report.get("stock") or {},
            "stage2": base.get("stage2") or selected_report.get("stage2") or {},
            "monitor": base.get("monitor") or selected_report.get("monitor") or {},
            "chart_artifacts": chart_artifacts,
            "chart_paths": chart_paths,
        }

    def _normalize_stock_analysis(self, analysis_report: Any) -> Dict[str, Any]:
        if isinstance(analysis_report, dict):
            return analysis_report
        text = str(analysis_report or "").strip()
        return {
            "raw_text": text,
            "final_verdict": self._extract_section_line(text, "1. Verdict") or self._extract_last_sentence(text),
        }

    def _extract_section_line(self, text: str, header: str) -> Optional[str]:
        pattern = rf"{re.escape(header)}\s*(.+?)(?:\n\d+\.\s|\Z)"
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        return " ".join(match.group(1).strip().split())

    def _extract_last_sentence(self, text: str) -> str:
        chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
        return chunks[-1] if chunks else ""

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    def _parse_execution_report(self, report_text: str) -> Dict[str, Any]:
        selected_security_id_raw = self._extract_header_value(report_text, "Selected Security ID", default="0")
        quantity_raw = self._extract_header_value(report_text, "Quantity", default="0")
        reference_price_raw = self._extract_header_value(report_text, "Reference Price", default="0")
        action_raw = self._extract_header_value(report_text, "Decision", default="AVOID")
        execution_status_raw = self._extract_header_value(report_text, "Execution Status", default="SKIPPED")
        trade_side_raw = self._extract_header_value(report_text, "Trade Side", default="AVOID")
        order_type_raw = self._extract_header_value(report_text, "Order Type", default="NONE")

        try:
            selected_security_id = int(re.findall(r"-?\d+", selected_security_id_raw)[0])
        except Exception:
            selected_security_id = 0

        try:
            quantity = int(re.findall(r"-?\d+", quantity_raw)[0])
        except Exception:
            quantity = 0

        try:
            reference_price = float(re.findall(r"-?\d+(?:\.\d+)?", reference_price_raw)[0])
        except Exception:
            reference_price = 0.0

        action = action_raw.strip().lower()
        if action not in {"trade", "avoid"}:
            action = "avoid"

        execution_status = execution_status_raw.strip().lower()
        if execution_status not in {"planned", "placed", "skipped", "blocked", "failed"}:
            execution_status = "skipped"

        trade_side = trade_side_raw.strip().lower()
        if trade_side not in {"buy", "sell", "avoid"}:
            trade_side = "avoid"

        order_type = order_type_raw.strip().upper()
        if order_type not in {"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET", "NONE"}:
            order_type = "NONE"

        return {
            "selected_security_id": selected_security_id,
            "selected_display_name": self._extract_header_value(report_text, "Selected Display Name", default="NONE"),
            "action": action,
            "execution_status": execution_status,
            "trade_side": trade_side,
            "order_type": order_type,
            "quantity": max(0, quantity),
            "reference_price": max(0.0, reference_price),
            "correlation_id": self._extract_header_value(report_text, "Correlation ID", default="NONE"),
            "order_id": self._extract_header_value(report_text, "Order ID", default="NONE"),
        }

    def _extract_header_value(self, report_text: str, header: str, default: str = "") -> str:
        next_headers = [
            "Decision",
            "Execution Status",
            "Selected Security ID",
            "Selected Display Name",
            "Trade Side",
            "Order Type",
            "Quantity",
            "Reference Price",
            "Correlation ID",
            "Order ID",
        ]
        alternatives = "|".join(re.escape(item) for item in next_headers)
        pattern = rf"(?is){re.escape(header)}\s*:\s*(.+?)(?=\s*(?:{alternatives})\s*:|\Z)"
        match = re.search(pattern, report_text)
        if not match:
            return default
        return " ".join(match.group(1).strip().split())

    def _should_refresh(self, existing: Optional[Dict[str, Any]], execution_packet: Dict[str, Any]) -> bool:
        if not existing:
            return True

        summary = existing.get("summary") or {}
        if summary.get("market_date") != execution_packet.get("market_date"):
            return True

        if int(summary.get("selected_security_id") or 0) != int(execution_packet["selected_stock"]["security_id"] or 0):
            return True

        existing_sources = summary.get("source_snapshots") or {}
        if existing_sources != execution_packet["summary"].get("source_snapshots"):
            return True

        generated_at = existing.get("generated_at_utc")
        if not generated_at:
            return True
        try:
            generated_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        except ValueError:
            return True
        age_seconds = (datetime.now(timezone.utc) - generated_dt).total_seconds()
        return age_seconds >= self.config.executioner_report_refresh_seconds

    def _save_no_trade_payload(self, market_date: str, risk_payload: Dict[str, Any], reason: str) -> Dict[str, Any]:
        payload = {
            "stage": "executioner",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "market_date": market_date,
                "status": "skipped",
                "selected_security_id": 0,
                "selected_display_name": "NONE",
                "action": "avoid",
                "trade_side": "avoid",
                "quantity": 0,
                "order_type": "NONE",
                "order_id": "NONE",
                "correlation_id": "NONE",
                "source_snapshots": {
                    "risk_analyzer_generated_at_utc": risk_payload.get("generated_at_utc"),
                },
                "chart_count": 0,
            },
            "execution_packet": None,
            "decision": {
                "selected_security_id": 0,
                "selected_display_name": "NONE",
                "action": "avoid",
                "execution_status": "skipped",
                "trade_side": "avoid",
                "order_type": "NONE",
                "quantity": 0,
                "reference_price": 0.0,
                "correlation_id": "NONE",
                "order_id": "NONE",
            },
            "report_text": reason,
        }
        self._save_payload(payload)
        print(f"Executioner skipped: {reason}")
        return payload

    def _load_required_snapshot(self, daily_path, latest_path, label: str) -> Dict[str, Any]:
        payload = self.storage.load_snapshot(daily_path)
        if payload:
            return payload
        payload = self.storage.load_snapshot(latest_path)
        if payload:
            return payload
        raise FileNotFoundError(f"{label} snapshot not found for executioner.")

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        self.storage.save_snapshot(self.config.executioner_latest_path, payload)
        self.storage.save_snapshot(
            self.config.executioner_daily_path(self.market_time.market_date_str()),
            payload,
        )


def main() -> None:
    config = PipelineConfig()
    runner = ExecutionerRunner(config)

    print("=" * 60)
    print("EXECUTIONER")
    print("=" * 60)
    print(f"Loop interval: {config.executioner_loop_interval_seconds} seconds")

    while True:
        try:
            runner.run_cycle()
        except Exception as exc:  # pragma: no cover - runtime safety
            print(f"Executioner cycle error: {type(exc).__name__}: {exc}")
        print(
            f"Sleeping for {config.executioner_loop_interval_seconds} seconds before next executioner cycle..."
        )
        time.sleep(config.executioner_loop_interval_seconds)


if __name__ == "__main__":
    main()
