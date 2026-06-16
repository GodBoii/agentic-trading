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

    def run_cycle(self, force: bool = False, trade_config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            print("AI trading is disabled. Executioner is idling.")
            return None

        market_date = self.market_time.market_date_str()
        stock_payload = self._load_required_snapshot(
            self.config.stock_analyzer_daily_path(market_date),
            self.config.stock_analyzer_latest_path,
            "Stock analyzer",
        )
        regime_payload = None
        if (stock_payload.get("summary") or {}).get("regime_analysis_enabled"):
            regime_payload = self._load_required_snapshot(
                self.config.regime_daily_path(market_date),
                self.config.regime_latest_path,
                "Regime",
            )

        stock_reports = list(stock_payload.get("reports") or [])
        if not stock_reports:
            return self._save_no_trade_payload(market_date, stock_payload, "No stock analyzer reports available.")

        stock_reports = stock_reports[: max(1, int(self.config.stock_analyzer_top_n))]
        fresh_snapshots = self._build_fresh_market_snapshots(stock_reports)

        execution_packets = [
            self._build_execution_packet(
                market_date,
                stock_payload,
                report,
                trade_config or {},
                fresh_snapshots.get(self._extract_report_security_id(report), {}),
                regime_payload=regime_payload,
            )
            for report in stock_reports[: max(1, int(self.config.stock_analyzer_top_n))]
        ]
        execution_packets = [packet for packet in execution_packets if packet]
        if not execution_packets:
            return self._save_no_trade_payload(market_date, stock_payload, "No executable stock packets available.")

        existing = self.storage.load_snapshot(self.config.executioner_latest_path)
        if not force and not self._should_refresh(existing, execution_packets):
            print("Executioner batch is still fresh.")
            return existing

        results: List[Dict[str, Any]] = []
        for index, packet in enumerate(execution_packets, 1):
            selected = packet["selected_stock"]
            print(f"[execution {index}] Evaluating {selected.get('display_name') or selected.get('symbol')}...")
            self.toolkit.set_allowed_security_id(int(selected.get("security_id") or 0))
            chart_paths = selected["chart_paths"]
            report_text = self.agent.analyze(packet, chart_paths, trade_config=trade_config)
            decision = self._parse_execution_report(report_text, packet)
            results.append(
                {
                    "rank": index,
                    "selected_stock": selected,
                    "execution_packet": packet,
                    "decision": decision,
                    "report_text": report_text,
                }
            )

        generated_utc = datetime.now(timezone.utc)
        generated_market = self.market_time.now()
        payload = {
            "stage": "executioner",
            "generated_at_utc": generated_utc.isoformat(),
            "generated_at_ist": generated_market.isoformat(),
            "summary": {
                "market_date": market_date,
                "market_timezone": self.config.market_timezone,
                "generated_at_ist": generated_market.isoformat(),
                "status": "completed",
                "executed_count": sum(1 for item in results if (item.get("decision") or {}).get("action") == "trade"),
                "evaluated_count": len(results),
                "selected_security_ids": [
                    int((item.get("selected_stock") or {}).get("security_id") or 0) for item in results
                ],
                "decisions": [item.get("decision") for item in results],
                "source_snapshots": {
                    "stock_analyzer_generated_at_utc": stock_payload.get("generated_at_utc"),
                },
                "chart_count": sum(len((item.get("selected_stock") or {}).get("chart_paths") or []) for item in results),
            },
            "results": results,
            "decision": {
                "action": "batch",
                "executed_count": sum(1 for item in results if (item.get("decision") or {}).get("action") == "trade"),
                "evaluated_count": len(results),
            },
            "report_text": self._build_batch_report(results),
        }
        self._save_payload(payload)
        print(f"Saved executioner batch snapshot for {len(results)} stock(s).")
        return payload

    def _build_execution_packet(
        self,
        market_date: str,
        stock_payload: Dict[str, Any],
        selected_report: Dict[str, Any],
        trade_config: Dict[str, Any],
        fresh_market_snapshot: Optional[Dict[str, Any]] = None,
        regime_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        selected_stock = self._normalize_selected_stock(selected_report)
        if not selected_stock["chart_paths"]:
            return None

        analysis_payload = selected_report.get("analysis_report")
        if analysis_payload is None:
            analysis_payload = selected_report.get("analysis")
        normalized_analysis = self._normalize_stock_analysis(analysis_payload)

        timing_context = self._build_timing_context(stock_payload)
        return {
            "market_date": market_date,
            "summary": {
                "source_snapshots": {
                    "stock_analyzer_generated_at_utc": stock_payload.get("generated_at_utc"),
                }
            },
            "timing_context": timing_context,
            "selected_stock": selected_stock,
            "regime_report": self._build_regime_report(regime_payload),
            "stock_analysis": normalized_analysis,
            "fresh_market_snapshot": fresh_market_snapshot or self._empty_fresh_market_snapshot(
                int(selected_stock.get("security_id") or 0),
                "fresh_snapshot_not_available",
            ),
            "account_context": self._build_account_context(),
            "user_profile": self.dhan.fetch_user_profile(),
            "trade_config": trade_config,
        }

    def _build_timing_context(self, stock_payload: Dict[str, Any]) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        now_market = self.market_time.now()
        stock_generated_at = stock_payload.get("generated_at_utc")
        age_seconds = self._age_seconds(stock_generated_at, now_utc)
        return {
            "stock_analyzer_generated_at_utc": stock_generated_at,
            "stock_analyzer_generated_at_ist": self._to_market_iso(stock_generated_at),
            "executioner_started_at_utc": now_utc.isoformat(),
            "executioner_started_at_ist": now_market.isoformat(),
            "current_market_time_ist": now_market.isoformat(),
            "market_timezone": self.config.market_timezone,
            "analysis_age_seconds": age_seconds,
            "analysis_age_human": self._human_age(age_seconds),
        }

    def _build_regime_report(self, regime_payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if not regime_payload:
            return None
        regime = regime_payload.get("regime") or {}
        report = str(regime.get("human_readable_report") or "").strip()
        if not report:
            return None
        lowered = report.lower()
        if "unavailable" in lowered or "fallback" in lowered or "invalid output" in lowered:
            return None
        return report

    def _build_fresh_market_snapshots(self, stock_reports: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        ids = [self._extract_report_security_id(report) for report in stock_reports]
        ids = [security_id for security_id in ids if security_id > 0]
        if not ids or not self.config.executioner_fresh_snapshot_enabled:
            return {
                security_id: self._empty_fresh_market_snapshot(security_id, "fresh_snapshot_disabled")
                for security_id in ids
            }
        unique_ids = list(dict.fromkeys(ids))
        fetched_at = datetime.now(timezone.utc)
        try:
            quotes = self.dhan.fetch_quote_batch(unique_ids, exchange_segment="BSE_EQ")
        except Exception as exc:
            quotes = {}
            quote_error = f"{type(exc).__name__}: {exc}"
        else:
            quote_error = None
        try:
            ohlc = self.dhan.fetch_ohlc_batch(unique_ids, exchange_segment="BSE_EQ")
        except Exception as exc:
            ohlc = {}
            ohlc_error = f"{type(exc).__name__}: {exc}"
        else:
            ohlc_error = None

        snapshots: Dict[int, Dict[str, Any]] = {}
        for security_id in unique_ids:
            quote_payload = quotes.get(security_id) or {}
            ohlc_payload = ohlc.get(security_id) or {}
            latest_price = self._extract_first_number(
                quote_payload,
                ("last_price", "lastPrice", "ltp", "LTP", "close", "price"),
            )
            bid_price = self._extract_first_number(quote_payload, ("bid_price", "bidPrice", "bestBidPrice", "bid"))
            ask_price = self._extract_first_number(quote_payload, ("ask_price", "askPrice", "bestAskPrice", "ask"))
            spread_percent = None
            if bid_price and ask_price and latest_price:
                spread_percent = round(((ask_price - bid_price) / latest_price) * 100.0, 4)
            latest_timestamp = self._extract_first_value(
                quote_payload,
                ("last_traded_time", "lastTradedTime", "lastTradeTime", "timestamp", "exchangeTime", "time"),
            )
            staleness_seconds = self._age_seconds(latest_timestamp, fetched_at)
            snapshots[security_id] = {
                "security_id": security_id,
                "exchange_segment": "BSE_EQ",
                "fetched_at_utc": fetched_at.isoformat(),
                "fetched_at_ist": fetched_at.astimezone(self.market_time.tz).isoformat(),
                "fetch_status": "success" if quote_payload or ohlc_payload else "failure",
                "fetch_errors": {
                    "quote": quote_error,
                    "ohlc": ohlc_error,
                },
                "latest_price": latest_price,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "spread_percent": spread_percent,
                "latest_market_timestamp": latest_timestamp,
                "latest_market_timestamp_ist": self._to_market_iso(latest_timestamp),
                "staleness_seconds": staleness_seconds,
                "is_stale": bool(
                    staleness_seconds is not None
                    and staleness_seconds > self.config.executioner_max_market_snapshot_staleness_seconds
                ),
                "quote": quote_payload,
                "ohlc": ohlc_payload,
            }
        return snapshots

    def _empty_fresh_market_snapshot(self, security_id: int, reason: str) -> Dict[str, Any]:
        return {
            "security_id": security_id,
            "exchange_segment": "BSE_EQ",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "fetched_at_ist": self.market_time.now().isoformat(),
            "fetch_status": "unavailable",
            "reason": reason,
            "latest_price": None,
            "bid_price": None,
            "ask_price": None,
            "spread_percent": None,
            "latest_market_timestamp": None,
            "latest_market_timestamp_ist": None,
            "staleness_seconds": None,
            "is_stale": None,
            "quote": {},
            "ohlc": {},
        }

    def _extract_report_security_id(self, selected_report: Dict[str, Any]) -> int:
        candidate = selected_report.get("candidate") or {}
        try:
            return int(candidate.get("security_id") or selected_report.get("security_id") or 0)
        except Exception:
            return 0

    def _extract_first_number(self, payload: Dict[str, Any], keys: tuple[str, ...]) -> Optional[float]:
        for key in keys:
            if key not in payload:
                continue
            try:
                return float(payload.get(key))
            except Exception:
                continue
        for value in payload.values():
            if isinstance(value, dict):
                nested = self._extract_first_number(value, keys)
                if nested is not None:
                    return nested
        return None

    def _extract_first_value(self, payload: Dict[str, Any], keys: tuple[str, ...]) -> Optional[Any]:
        for key in keys:
            if key in payload and payload.get(key) not in (None, ""):
                return payload.get(key)
        for value in payload.values():
            if isinstance(value, dict):
                nested = self._extract_first_value(value, keys)
                if nested not in (None, ""):
                    return nested
        return None

    def _age_seconds(self, value: Any, now: Optional[datetime] = None) -> Optional[float]:
        if not value:
            return None
        try:
            if isinstance(value, (int, float)):
                candidate = float(value)
                if candidate > 10_000_000_000:
                    candidate = candidate / 1000.0
                dt = datetime.fromtimestamp(candidate, tz=timezone.utc)
            else:
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
            if isinstance(value, (int, float)):
                candidate = float(value)
                if candidate > 10_000_000_000:
                    candidate = candidate / 1000.0
                dt = datetime.fromtimestamp(candidate, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(self.market_time.tz).isoformat()
        except Exception:
            return None

    def _human_age(self, age_seconds: Optional[float]) -> Optional[str]:
        if age_seconds is None:
            return None
        seconds = max(0, int(age_seconds))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes}m {sec}s"
        if minutes:
            return f"{minutes}m {sec}s"
        return f"{sec}s"

    def _build_account_context(self) -> Dict[str, Any]:
        holdings = self.dhan.fetch_holdings()
        positions = self.dhan.fetch_positions()
        fund_limits = self.dhan.fetch_fund_limits()

        holdings_rows = holdings.get("data") if isinstance(holdings.get("data"), list) else []
        positions_rows = positions.get("data") if isinstance(positions.get("data"), list) else []
        raw_fund_data = fund_limits.get("data") if isinstance(fund_limits.get("data"), dict) else {}
        fund_data = raw_fund_data.get("data") if isinstance(raw_fund_data.get("data"), dict) else raw_fund_data

        return {
            "holdings": {"status": holdings.get("status"), "count": len(holdings_rows), "items": holdings_rows},
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
            "funds": {"status": fund_limits.get("status"), "data": fund_data},
            "fetch_status": {
                "holdings": holdings.get("status"),
                "positions": positions.get("status"),
                "funds": fund_limits.get("status"),
            },
        }

    def _normalize_selected_stock(self, selected_report: Dict[str, Any]) -> Dict[str, Any]:
        candidate = selected_report.get("candidate") or {}
        base = candidate if candidate else selected_report
        chart_artifacts = base.get("chart_artifacts") or selected_report.get("chart_artifacts") or {}
        charts = chart_artifacts.get("charts") or {}

        chart_paths: List[str] = []
        ordered = chart_artifacts.get("chart_paths_ordered")
        if ordered and isinstance(ordered, list):
            chart_paths = [str(p) for p in ordered]
        else:
            preferred_order = [
                "current_1m",
                "current_5m",
                "current_15m",
                "current_30m",
                "current_1h",
                "previous_5m",
                "previous_15m",
                "previous_1h",
            ]
            for key in preferred_order:
                path = (charts.get(key) or {}).get("path")
                if path:
                    chart_paths.append(str(path))
            if not chart_paths:
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

    def _parse_execution_report(
        self,
        report_text: str,
        execution_packet: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        selected_stock = (execution_packet or {}).get("selected_stock") or {}
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
            selected_security_id = int(selected_stock.get("security_id") or 0)

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
            action = self._infer_action(report_text)

        execution_status = execution_status_raw.strip().lower()
        if execution_status not in {"planned", "placed", "skipped", "blocked", "failed"}:
            if "failed" in execution_status or "rejected" in execution_status:
                execution_status = "failed"
            elif "blocked" in execution_status:
                execution_status = "blocked"
            elif "placed" in execution_status:
                execution_status = "placed"
            elif "planned" in execution_status:
                execution_status = "planned"
            else:
                execution_status = self._infer_execution_status(report_text)

        trade_side = trade_side_raw.strip().lower()
        if trade_side not in {"buy", "sell", "avoid"}:
            trade_side = self._infer_trade_side(report_text)

        order_type = order_type_raw.strip().upper()
        if order_type not in {"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET", "NONE"}:
            order_type = "NONE"

        return {
            "selected_security_id": selected_security_id,
            "selected_display_name": self._extract_header_value(
                report_text,
                "Selected Display Name",
                default=str(selected_stock.get("display_name") or "NONE"),
            ),
            "action": action,
            "execution_status": execution_status,
            "trade_side": trade_side,
            "order_type": order_type,
            "quantity": max(0, quantity),
            "reference_price": max(0.0, reference_price),
            "correlation_id": self._extract_header_value(report_text, "Correlation ID", default="NONE"),
            "order_id": self._extract_header_value(report_text, "Order ID", default="NONE"),
        }

    def _infer_action(self, report_text: str) -> str:
        text = report_text.lower()
        if any(term in text for term in ("avoid", "skipped", "blocked", "failed", "not placed", "no order")):
            return "avoid"
        if any(term in text for term in ("placed", "order id", "planned", "trade", "executed")):
            return "trade"
        return "avoid"

    def _infer_execution_status(self, report_text: str) -> str:
        text = report_text.lower()
        if "failed" in text or "rejected" in text:
            return "failed"
        if "blocked" in text:
            return "blocked"
        if "not placed" in text or "no order placed" in text or "order id: n/a" in text or "order id:** n/a" in text:
            return "skipped"
        if "placed" in text or "order id" in text or "executed" in text:
            return "placed"
        if "planned" in text:
            return "planned"
        return "skipped"

    def _infer_trade_side(self, report_text: str) -> str:
        text = report_text.lower()
        if "buy" in text or "long" in text:
            return "buy"
        if "sell" in text or "short" in text:
            return "sell"
        return "avoid"

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
            bold_pattern = rf"(?is)\*+\s*{re.escape(header)}\s*\*+\s*:\s*(.+?)(?=\s*(?:[-*]\s*)?\*+\s*(?:{alternatives})\s*\*+\s*:|\s*(?:{alternatives})\s*:|\Z)"
            match = re.search(bold_pattern, report_text)
        if not match:
            return default
        value = " ".join(match.group(1).strip().split())
        return value.strip(" -*")

    def _build_batch_report(self, results: List[Dict[str, Any]]) -> str:
        chunks = []
        for item in results:
            stock = item.get("selected_stock") or {}
            decision = item.get("decision") or {}
            chunks.append(
                f"{item.get('rank')}. {stock.get('display_name') or stock.get('symbol')} - "
                f"{decision.get('action')} / {decision.get('execution_status')} / "
                f"qty={decision.get('quantity')}"
            )
        return "\n".join(chunks)

    def _should_refresh(self, existing: Optional[Dict[str, Any]], execution_packets: List[Dict[str, Any]]) -> bool:
        if not existing:
            return True

        summary = existing.get("summary") or {}
        if summary.get("market_date") != execution_packets[0].get("market_date"):
            return True

        expected_ids = [int(packet["selected_stock"]["security_id"] or 0) for packet in execution_packets]
        actual_ids = [int(item) for item in summary.get("selected_security_ids") or []]
        if actual_ids != expected_ids:
            return True

        existing_sources = summary.get("source_snapshots") or {}
        if existing_sources != execution_packets[0]["summary"].get("source_snapshots"):
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

    def _save_no_trade_payload(self, market_date: str, stock_payload: Dict[str, Any], reason: str) -> Dict[str, Any]:
        generated_utc = datetime.now(timezone.utc)
        generated_market = self.market_time.now()
        payload = {
            "stage": "executioner",
            "generated_at_utc": generated_utc.isoformat(),
            "generated_at_ist": generated_market.isoformat(),
            "summary": {
                "market_date": market_date,
                "market_timezone": self.config.market_timezone,
                "generated_at_ist": generated_market.isoformat(),
                "status": "skipped",
                "executed_count": 0,
                "evaluated_count": 0,
                "selected_security_ids": [],
                "decisions": [],
                "source_snapshots": {
                    "stock_analyzer_generated_at_utc": stock_payload.get("generated_at_utc"),
                },
                "chart_count": 0,
            },
            "results": [],
            "decision": {"action": "avoid", "executed_count": 0, "evaluated_count": 0},
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
