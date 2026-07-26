from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pipeline.config import PipelineConfig
from pipeline.runtime.run_executioner import ExecutionerRunner
from pipeline.runtime.run_stock_analyzer import MultiStockAnalyzerRunner
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.cloud_persistence_service import CloudPersistenceService
from pipeline.services.dhan_execution_toolkit import DhanExecutionToolkit
from pipeline.services.dhan_service import DhanService
from pipeline.stock import StockAgent


class MultiStockAgentRunner(MultiStockAnalyzerRunner):
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        super().__init__(config, initialize_agent=False)
        self.execution_helper = ExecutionerRunner(self.config, initialize_agent=False)

    def run_cycle(
        self,
        force: bool = False,
        trade_config: Optional[Dict[str, Any]] = None,
        use_regime_analysis: Optional[bool] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        run_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            print("AI trading is disabled. Stock agent is idling.")
            return None

        effective_run_context = dict(run_context or {})
        if not effective_run_context.get("trade_session_id"):
            generated_id = f"auto-{int(time.time() * 1000)}"
            effective_run_context["trade_session_id"] = generated_id
            effective_run_context.setdefault("request_id", generated_id)

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
        account_context = self._build_account_context()
        effective_trade_config = self._with_effective_trade_amount(trade_config, account_context)
        selected_candidates, candidate_source = self._select_candidates(
            stage2_payload,
            None,
            effective_trade_config,
        )
        self._emit(
            event_callback,
            {
                "type": "stock_agent_selection",
                "candidate_source": candidate_source,
                "selected_count": len(selected_candidates),
                "selected": [
                    {
                        "rank": index + 1,
                        "security_id": item.get("security_id"),
                        "symbol": item.get("symbol"),
                        "display_name": item.get("display_name"),
                        "manual_margin_filter": item.get("manual_margin_filter"),
                    }
                    for index, item in enumerate(selected_candidates)
                ],
            },
        )
        if not selected_candidates:
            self._emit(
                event_callback,
                {
                    "type": "stock_agent_no_trade",
                    "reason": "No Stage 2 top-30 stocks met the manual intraday margin budget.",
                },
            )
            return self._save_no_trade_payload(
                market_date,
                candidate_source,
                regime_enabled,
                "No Stage 2 top-30 stocks met the manual intraday margin budget.",
            )

        candidate_packets = [
            self._build_candidate_packet(
                market_date=market_date,
                candidate_record=candidate_record,
                candidate_source=candidate_source,
                stage2_payload=stage2_payload,
                monitor_payload=None,
                regime_payload=regime_payload,
                regime_enabled=regime_enabled,
                account_context=account_context,
            )
            for candidate_record in selected_candidates
        ]
        for packet in candidate_packets:
            self._strip_monitor_context(packet)

        existing = self.storage.load_snapshot(self.config.stock_agent_latest_path)
        if not force and not self._should_refresh(existing, candidate_packets):
            print("Stock agent batch is still fresh.")
            return existing

        results = self._run_stock_agents(
            candidate_packets,
            effective_trade_config or {},
            event_callback,
            effective_run_context,
        )
        generated_utc = datetime.now(timezone.utc)
        generated_market = self.market_time.now()
        payload = {
            "stage": "stock_agent",
            "generated_at_utc": generated_utc.isoformat(),
            "generated_at_ist": generated_market.isoformat(),
            "summary": {
                "market_date": market_date,
                "market_timezone": self.config.market_timezone,
                "generated_at_ist": generated_market.isoformat(),
                "candidate_source": candidate_source,
                "status": "completed",
                "selected_count": len(results),
                "evaluated_count": len(results),
                "executed_count": sum(1 for item in results if (item.get("decision") or {}).get("action") == "trade"),
                "selected_symbols": [(item.get("candidate") or {}).get("symbol") for item in results],
                "selected_security_ids": [
                    int((item.get("candidate") or {}).get("security_id") or 0) for item in results
                ],
                "decisions": [item.get("decision") for item in results],
                "source_snapshots": candidate_packets[0]["source_snapshots"],
                "regime_analysis_enabled": regime_enabled,
                "chart_count": sum(int((item.get("candidate") or {}).get("chart_artifacts", {}).get("chart_count", 0)) for item in results),
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
        print(f"Saved stock agent batch snapshot for {len(results)} stock(s).")
        return payload

    def _select_candidates(
        self,
        stage2_payload: Dict[str, Any],
        monitor_payload: Optional[Dict[str, Any]],
        trade_config: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], str]:
        if not self._is_manual_mode(trade_config):
            return super()._select_candidates(stage2_payload, monitor_payload, trade_config)

        scan_limit = max(1, int(self.config.stock_agent_manual_scan_limit))
        stage2_stocks = self._build_stage2_selection_pool(stage2_payload)[:scan_limit]
        filtered_stocks = self._filter_by_manual_margin_budget(stage2_stocks, trade_config)
        return filtered_stocks, "stage2_manual_margin_filter"

    def _strip_monitor_context(self, packet: Dict[str, Any]) -> None:
        packet.pop("monitor", None)
        snapshots = packet.get("source_snapshots")
        if isinstance(snapshots, dict):
            snapshots.pop("monitor_generated_at_utc", None)
            snapshots.pop("monitor_generated_at_ist", None)
        timing = packet.get("timing_context")
        if isinstance(timing, dict):
            source_times = timing.get("source_snapshot_times")
            if isinstance(source_times, dict):
                source_times.pop("monitor_generated_at_utc", None)
                source_times.pop("monitor_generated_at_ist", None)
            source_ages = timing.get("source_snapshot_ages_seconds")
            if isinstance(source_ages, dict):
                source_ages.pop("monitor", None)

    def _filter_by_manual_margin_budget(
        self,
        stocks: List[Dict[str, Any]],
        trade_config: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        trade_amount = (trade_config or {}).get("trade_amount")
        try:
            margin_budget = float(trade_amount)
        except Exception:
            return []
        if margin_budget <= 0:
            return []

        filtered: List[Dict[str, Any]] = []
        for stock in stocks:
            reference_price = self._reference_price(stock)
            if reference_price <= 0:
                continue
            margin_results = [
                self._calculate_one_share_margin(stock, side, reference_price)
                for side in ("BUY", "SELL")
            ]
            valid_results = [item for item in margin_results if item.get("status") == "success"]
            if not valid_results:
                continue
            best_margin = min(float(item["total_margin"]) for item in valid_results)
            enriched = dict(stock)
            enriched["manual_margin_filter"] = {
                "margin_budget": margin_budget,
                "reference_price": reference_price,
                "best_one_share_margin": best_margin,
                "included": best_margin <= margin_budget,
                "sides": margin_results,
            }
            if best_margin <= margin_budget:
                filtered.append(enriched)
        return filtered

    def _calculate_one_share_margin(self, stock: Dict[str, Any], side: str, reference_price: float) -> Dict[str, Any]:
        security_id = int(stock.get("security_id") or 0)
        try:
            response = self.execution_helper.dhan.calculate_margin_requirement(
                security_id=security_id,
                exchange_segment="BSE_EQ",
                transaction_type=side,
                quantity=1,
                product_type="INTRADAY",
                price=float(reference_price),
                trigger_price=0.0,
            )
            total_margin = self._extract_total_margin(response)
            if total_margin is None or total_margin <= 0:
                return {"side": side, "status": "failure", "total_margin": None, "response": response}
            return {"side": side, "status": "success", "total_margin": total_margin, "response": response}
        except Exception as exc:
            return {"side": side, "status": "failure", "total_margin": None, "error": f"{type(exc).__name__}: {exc}"}

    def _extract_total_margin(self, response: Dict[str, Any]) -> Optional[float]:
        candidates: List[Any] = []
        if isinstance(response, dict):
            candidates.append(response)
            data = response.get("data")
            if isinstance(data, dict):
                candidates.append(data)
                nested = data.get("data")
                if isinstance(nested, dict):
                    candidates.append(nested)
        for candidate in candidates:
            for key in ("totalMargin", "total_margin", "marginRequired", "margin_required"):
                try:
                    if candidate.get(key) not in (None, ""):
                        return float(candidate.get(key))
                except Exception:
                    continue
        return None

    def _reference_price(self, stock: Dict[str, Any]) -> float:
        for key in ("price", "close", "ltp", "last_price", "lastPrice"):
            try:
                value = float(stock.get(key) or 0)
                if value > 0:
                    return value
            except Exception:
                continue
        return 0.0

    def _run_stock_agents(
        self,
        candidate_packets: List[Dict[str, Any]],
        trade_config: Dict[str, Any],
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        run_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        max_workers = max(1, len(candidate_packets))
        results: Dict[int, Dict[str, Any]] = {}
        failures: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(
                    self._run_single_stock_agent,
                    index,
                    packet,
                    trade_config,
                    event_callback,
                    run_context or {},
                ): index
                for index, packet in enumerate(candidate_packets)
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
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
                    self._emit(event_callback, {"type": "stock_agent_failed", **failures[-1]})

        if failures:
            print(f"Stock agent skipped {len(failures)} candidate(s): {failures}")

        ordered_results = [results[index] for index in sorted(results.keys())]
        if ordered_results:
            return ordered_results

        auth_failures = [item for item in failures if "stock_agent_auth_invalid::" in str(item.get("error"))]
        if auth_failures:
            raise RuntimeError(auth_failures[0]["error"])
        raise RuntimeError(f"stock_agent_all_candidates_failed::{failures}")

    def _run_single_stock_agent(
        self,
        index: int,
        candidate_packet: Dict[str, Any],
        trade_config: Dict[str, Any],
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        run_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        security_id = int(candidate_packet["security_id"])
        CloudPersistenceService.validate_agno_db()
        self._emit(
            event_callback,
            {
                "type": "stock_agent_started",
                "rank": index + 1,
                "security_id": security_id,
                "symbol": candidate_packet.get("symbol"),
                "display_name": candidate_packet.get("display_name"),
                "message": "Fetching intraday history and building charts.",
            },
        )
        intraday_resp = self.dhan.fetch_intraday_history(
            security_id,
            days=5,
            interval=1,
            exchange_segment="BSE_EQ",
            instrument_candidates=[candidate_packet.get("instrument"), "EQUITY"],
        )
        if not intraday_resp or str(intraday_resp.get("status", "")).lower() != "success":
            remarks = intraday_resp.get("remarks") if isinstance(intraday_resp, dict) else None
            if self.dhan.is_auth_invalid(intraday_resp):
                raise RuntimeError(f"stock_agent_auth_invalid::{remarks}")
            raise RuntimeError(f"stock_agent_intraday_history_failed::{security_id}::{remarks}")

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
        chart_paths = chart_bundle.get("chart_paths_ordered", [])
        if not chart_paths:
            chart_paths = [info["path"] for info in chart_bundle.get("charts", {}).values()]
        cloud_image_urls = self._upload_chart_images(
            index + 1,
            candidate_packet,
            chart_bundle,
            chart_paths,
            run_context or {},
        )
        self._emit(
            event_callback,
            {
                "type": "stock_agent_charts_ready",
                "rank": index + 1,
                "security_id": security_id,
                "symbol": candidate_packet.get("symbol"),
                "display_name": candidate_packet.get("display_name"),
                "chart_count": len(chart_paths),
                "attachments": {"images": self._chart_image_cards(chart_bundle), "files": []},
                "chart_artifacts": chart_bundle,
                "message": "Charts are ready; running stock agent.",
            },
        )

        selected_stock = self.execution_helper._normalize_selected_stock(
            {"rank": index + 1, "candidate": candidate_packet}
        )
        isolated_dhan = DhanService(self.config, prefer_gateway=False)
        toolkit = DhanExecutionToolkit(isolated_dhan, entry_only=True)
        toolkit.set_allowed_security_id(security_id)
        agent = StockAgent(toolkit)
        fresh_market_snapshot = self._build_fresh_market_snapshot(security_id, isolated_dhan)
        stock_packet = {
            "market_date": candidate_packet.get("market_date"),
            "summary": {"source_snapshots": candidate_packet.get("source_snapshots")},
            "timing_context": self._build_stock_agent_timing_context(candidate_packet),
            "candidate": candidate_packet,
            "selected_stock": selected_stock,
            "regime_report": candidate_packet.get("regime_report"),
            "fresh_market_snapshot": fresh_market_snapshot,
            "account_context": candidate_packet.get("account_context") or self._build_account_context(),
            "user_profile": isolated_dhan.fetch_user_profile(),
            "trade_config": trade_config,
        }

        print(f"[stock agent {index + 1}] Analyzing and trading {candidate_packet['display_name']}...")
        agent_run_context = {
            **(run_context or {}),
            "agno_session_id": self._agno_session_id(
                run_context or {},
                index + 1,
                security_id,
            ),
            "stage": "stock_agent",
            "rank": index + 1,
            "security_id": security_id,
            "symbol": candidate_packet.get("symbol"),
            "display_name": candidate_packet.get("display_name"),
            "image_storage_paths": [
                card.get("storage_path")
                for card in self._chart_image_cards(chart_bundle)
                if card.get("storage_path")
            ],
        }
        report_text = agent.analyze(
            stock_packet,
            cloud_image_urls,
            trade_config=trade_config,
            run_context=agent_run_context,
        )
        decision = self.execution_helper._parse_execution_report(report_text, stock_packet)
        attachments = self._build_agent_attachments(index + 1, candidate_packet, stock_packet, chart_bundle)
        result = {
            "rank": index + 1,
            "candidate": candidate_packet,
            "selected_stock": selected_stock,
            "stock_packet": stock_packet,
            "decision": decision,
            "attachments": attachments,
            "agent_metadata": agent.last_run_metadata,
            "analysis": report_text,
            "report_text": report_text,
        }
        self._emit(
            event_callback,
            {
                "type": "stock_agent_completed",
                "rank": index + 1,
                "security_id": security_id,
                "symbol": candidate_packet.get("symbol"),
                "display_name": candidate_packet.get("display_name"),
                "decision": decision,
                "attachments": attachments,
                "agent_metadata": agent.last_run_metadata,
                "report_text": report_text,
            },
        )
        return result

    def _chart_image_cards(self, chart_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        charts = chart_bundle.get("charts") if isinstance(chart_bundle, dict) else {}
        if not isinstance(charts, dict):
            return []
        cards: List[Dict[str, Any]] = []
        order = list(chart_bundle.get("chart_paths_ordered") or [])
        by_path = {
            str(info.get("path")): (key, info)
            for key, info in charts.items()
            if isinstance(info, dict) and info.get("path")
        }
        ordered_items = []
        for chart_path in order:
            if str(chart_path) in by_path:
                ordered_items.append(by_path[str(chart_path)])
        for key, info in charts.items():
            if isinstance(info, dict) and not any(existing_key == key for existing_key, _ in ordered_items):
                ordered_items.append((key, info))
        for key, info in ordered_items:
            cards.append(
                {
                    "id": key,
                    "title": f"{str(info.get('day_type') or '').title()} {info.get('label') or ''}".strip(),
                    "filename": Path(str(info.get("path") or "")).name,
                    "path": info.get("path"),
                    "storage_path": info.get("storage_path"),
                    "cloud_url": info.get("cloud_url"),
                    "day_type": info.get("day_type"),
                    "date": info.get("date"),
                    "timeframe": info.get("label"),
                    "candles": info.get("candles"),
                }
            )
        return cards

    def _upload_chart_images(
        self,
        rank: int,
        candidate_packet: Dict[str, Any],
        chart_bundle: Dict[str, Any],
        chart_paths: List[str],
        run_context: Dict[str, Any],
    ) -> List[str]:
        trade_session_id = str(run_context.get("trade_session_id") or "").strip()
        if not trade_session_id:
            raise RuntimeError("stock_agent_trade_session_id_required_for_cloud_images")

        agent_slug = self._slugify(
            candidate_packet.get("display_name")
            or candidate_packet.get("symbol")
            or f"agent-{rank}"
        )
        chart_records = chart_bundle.get("charts") if isinstance(chart_bundle, dict) else {}
        by_path = {
            str(info.get("path")): info
            for info in (chart_records or {}).values()
            if isinstance(info, dict) and info.get("path")
        }
        cloud_urls: List[str] = []
        for chart_path in chart_paths:
            filename = Path(str(chart_path)).name
            storage_path = (
                f"{trade_session_id}/agents/{rank}-{agent_slug}/images/{filename}"
            )
            uploaded = CloudPersistenceService.upload_image(chart_path, storage_path)
            cloud_urls.append(uploaded["cloud_url"])
            chart_info = by_path.get(str(chart_path))
            if isinstance(chart_info, dict):
                chart_info.update(uploaded)

        chart_bundle["cloud_image_urls_ordered"] = cloud_urls
        return cloud_urls

    def _agno_session_id(
        self,
        run_context: Dict[str, Any],
        rank: int,
        security_id: int,
    ) -> str:
        trade_session_id = str(run_context.get("trade_session_id") or "").strip()
        if not trade_session_id:
            raise RuntimeError("stock_agent_trade_session_id_required_for_agno")
        return f"{trade_session_id}--stock-{rank}-{security_id}"

    def _build_agent_attachments(
        self,
        rank: int,
        candidate_packet: Dict[str, Any],
        stock_packet: Dict[str, Any],
        chart_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        display_name = candidate_packet.get("display_name") or candidate_packet.get("symbol") or f"Agent {rank}"
        return {
            "images": self._chart_image_cards(chart_bundle),
            "files": [
                {
                    "id": "instructions",
                    "title": "Instructions",
                    "filename": "instructions.md",
                    "content_type": "text/markdown",
                    "content": self._build_instructions_markdown(display_name, stock_packet),
                },
                {
                    "id": "data",
                    "title": "Data",
                    "filename": "data.md",
                    "content_type": "text/markdown",
                    "content": self._build_data_markdown(display_name, stock_packet),
                },
            ],
        }

    def _build_instructions_markdown(self, display_name: str, stock_packet: Dict[str, Any]) -> str:
        trade_config = stock_packet.get("trade_config") or {}
        selected_stock = stock_packet.get("selected_stock") or {}
        lines = [
            f"# {display_name} Agent Instructions",
            "",
            "- Analyze the assigned intraday Indian equity candidate.",
            "- Use chart images and technical metadata as the primary current market evidence.",
            "- Use current 1m/5m charts for execution timing and higher timeframes for structure.",
            "- Check existing orders and positions for the selected security before any new entry.",
            "- Use Dhan margin and order tools before any live placement.",
            "- Prefer protected intraday Super Orders when available.",
            "- Stop after one protected-order attempt and one fallback normal-entry attempt.",
            "- Return parseable Decision and Execution Status headers exactly once.",
            "",
            "## Selected Stock",
            "```json",
            json.dumps(selected_stock, indent=2, ensure_ascii=True, default=str),
            "```",
            "",
            "## Trade Config",
            "```json",
            json.dumps(trade_config, indent=2, ensure_ascii=True, default=str),
            "```",
        ]
        return "\n".join(lines)

    def _build_data_markdown(self, display_name: str, stock_packet: Dict[str, Any]) -> str:
        candidate = stock_packet.get("candidate") or {}
        data = {
            "display_name": display_name,
            "market_date": stock_packet.get("market_date"),
            "timing_context": stock_packet.get("timing_context"),
            "selected_stock": stock_packet.get("selected_stock"),
            "technical_metadata": (candidate.get("chart_artifacts") or {}).get("technical_metadata"),
            "stage2": candidate.get("stage2"),
            "fresh_market_snapshot": stock_packet.get("fresh_market_snapshot"),
            "account_context": stock_packet.get("account_context"),
        }
        return "\n".join(
            [
                f"# {display_name} Agent Data",
                "",
                "```json",
                json.dumps(data, indent=2, ensure_ascii=True, default=str),
                "```",
            ]
        )

    def _build_stock_agent_timing_context(self, candidate_packet: Dict[str, Any]) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        context = dict(candidate_packet.get("timing_context") or {})
        context.update(
            {
                "stock_agent_started_at_utc": now_utc.isoformat(),
                "stock_agent_started_at_ist": now_utc.astimezone(self.market_time.tz).isoformat(),
                "current_market_time_ist": self.market_time.now().isoformat(),
            }
        )
        source_times = dict(context.get("source_snapshot_times") or {})
        source_times.pop("monitor_generated_at_utc", None)
        source_times.pop("monitor_generated_at_ist", None)
        context["source_snapshot_times"] = source_times
        source_ages = dict(context.get("source_snapshot_ages_seconds") or {})
        source_ages.pop("monitor", None)
        context["source_snapshot_ages_seconds"] = source_ages
        return context

    def _build_fresh_market_snapshot(self, security_id: int, dhan: DhanService) -> Dict[str, Any]:
        if not self.config.executioner_fresh_snapshot_enabled:
            return self.execution_helper._empty_fresh_market_snapshot(security_id, "fresh_snapshot_disabled")
        fetched_at = datetime.now(timezone.utc)
        try:
            quotes = dhan.fetch_quote_batch([security_id], exchange_segment="BSE_EQ")
            quote_error = None
        except Exception as exc:
            quotes = {}
            quote_error = f"{type(exc).__name__}: {exc}"
        try:
            ohlc = dhan.fetch_ohlc_batch([security_id], exchange_segment="BSE_EQ")
            ohlc_error = None
        except Exception as exc:
            ohlc = {}
            ohlc_error = f"{type(exc).__name__}: {exc}"

        quote_payload = quotes.get(security_id) or {}
        ohlc_payload = ohlc.get(security_id) or {}
        latest_price = self.execution_helper._extract_first_number(
            quote_payload,
            ("last_price", "lastPrice", "ltp", "LTP", "close", "price"),
        )
        bid_price = self.execution_helper._extract_first_number(quote_payload, ("bid_price", "bidPrice", "bestBidPrice", "bid"))
        ask_price = self.execution_helper._extract_first_number(quote_payload, ("ask_price", "askPrice", "bestAskPrice", "ask"))
        spread_percent = None
        if bid_price and ask_price and latest_price:
            spread_percent = round(((ask_price - bid_price) / latest_price) * 100.0, 4)
        latest_timestamp = self.execution_helper._extract_first_value(
            quote_payload,
            ("last_traded_time", "lastTradedTime", "lastTradeTime", "timestamp", "exchangeTime", "time"),
        )
        staleness_seconds = self.execution_helper._age_seconds(latest_timestamp, fetched_at)
        return {
            "security_id": security_id,
            "exchange_segment": "BSE_EQ",
            "fetched_at_utc": fetched_at.isoformat(),
            "fetched_at_ist": fetched_at.astimezone(self.market_time.tz).isoformat(),
            "fetch_status": "success" if quote_payload or ohlc_payload else "failure",
            "fetch_errors": {"quote": quote_error, "ohlc": ohlc_error},
            "latest_price": latest_price,
            "bid_price": bid_price,
            "ask_price": ask_price,
            "spread_percent": spread_percent,
            "latest_market_timestamp": latest_timestamp,
            "latest_market_timestamp_ist": self.execution_helper._to_market_iso(latest_timestamp),
            "staleness_seconds": staleness_seconds,
            "is_stale": bool(
                staleness_seconds is not None
                and staleness_seconds > self.config.executioner_max_market_snapshot_staleness_seconds
            ),
            "quote": quote_payload,
            "ohlc": ohlc_payload,
        }

    def _save_no_trade_payload(
        self,
        market_date: str,
        candidate_source: str,
        regime_enabled: bool,
        reason: str,
    ) -> Dict[str, Any]:
        generated_utc = datetime.now(timezone.utc)
        generated_market = self.market_time.now()
        payload = {
            "stage": "stock_agent",
            "generated_at_utc": generated_utc.isoformat(),
            "generated_at_ist": generated_market.isoformat(),
            "summary": {
                "market_date": market_date,
                "market_timezone": self.config.market_timezone,
                "generated_at_ist": generated_market.isoformat(),
                "candidate_source": candidate_source,
                "status": "skipped",
                "selected_count": 0,
                "evaluated_count": 0,
                "executed_count": 0,
                "selected_symbols": [],
                "selected_security_ids": [],
                "decisions": [],
                "regime_analysis_enabled": regime_enabled,
                "chart_count": 0,
            },
            "results": [],
            "decision": {"action": "avoid", "executed_count": 0, "evaluated_count": 0},
            "report_text": reason,
        }
        self._save_payload(payload)
        print(f"Stock agent skipped: {reason}")
        return payload

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        self.storage.save_snapshot(self.config.stock_agent_latest_path, payload)
        self.storage.save_snapshot(
            self.config.stock_agent_daily_path(self.market_time.market_date_str()),
            payload,
        )

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

    def _emit(
        self,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        event: Dict[str, Any],
    ) -> None:
        if not event_callback:
            return
        try:
            event_callback(event)
        except Exception:
            pass


def main() -> None:
    config = PipelineConfig()
    runner = MultiStockAgentRunner(config)

    print("=" * 60)
    print("STOCK AGENT")
    print("=" * 60)
    print(f"Loop interval: {config.stock_analyzer_loop_interval_seconds} seconds")
    print("Manual agents: all top-30 stocks within entered margin budget")
    print(f"Manual scan limit: {config.stock_agent_manual_scan_limit}")

    while True:
        try:
            runner.run_cycle()
        except Exception as exc:  # pragma: no cover - runtime safety
            print(f"Stock agent cycle error: {type(exc).__name__}: {exc}")
        print(
            f"Sleeping for {config.stock_analyzer_loop_interval_seconds} seconds before next stock agent cycle..."
        )
        time.sleep(config.stock_analyzer_loop_interval_seconds)


if __name__ == "__main__":
    main()
