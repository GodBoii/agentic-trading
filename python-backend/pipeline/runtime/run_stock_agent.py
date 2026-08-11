from __future__ import annotations

import os
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
from pipeline.services.dhan_service import DhanService
from pipeline.services.trading_amount_service import TradingAmountService
from pipeline.stock import StockAgent
from pipeline.stock.toolkits import (
    StockAccountToolkit,
    StockExecutionCoordinator,
    StockExecutionToolkit,
    StockMarketDataToolkit,
    StockTechnicalToolkit,
)


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
                    "reason": "No Stage 2 candidates were affordable within the saved trading amount.",
                },
            )
            return self._save_no_trade_payload(
                market_date,
                candidate_source,
                regime_enabled,
                "No Stage 2 candidates were affordable within the saved trading amount.",
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
                "executed_count": sum(1 for item in results if self._is_placed_result(item)),
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
                "executed_count": sum(1 for item in results if self._is_placed_result(item)),
                "evaluated_count": len(results),
            },
            "report_text": self._build_batch_report(results),
        }
        self._save_payload(payload)
        print(f"Saved stock agent batch snapshot for {len(results)} stock(s).")
        return payload

    def run_event(
        self,
        event: Dict[str, Any],
        *,
        user_id: Optional[str] = None,
        trade_config: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Run exactly one Intra-Finder-qualified stock through the agent."""
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            raise RuntimeError("ai_trading_disabled")
        market_date = self.market_time.market_date_str()
        if str(event.get("market_date") or "") != market_date:
            raise RuntimeError("stale_intra_finder_event")
        if str(event.get("exchange_segment") or "").upper() not in {"NSE_EQ", "BSE_EQ"}:
            raise RuntimeError("event_missing_valid_exchange_segment")

        account_context = self._build_account_context()
        trade_config = dict(trade_config or {})
        trade_config["trade_mode"] = str(trade_config.get("trade_mode") or "auto").lower()
        trade_config["trade_amount"] = TradingAmountService.parse(trade_config.get("trade_amount"))
        trade_config["user_id"] = user_id
        if trade_config["trade_amount"] is None:
            raise RuntimeError("trading_amount_missing_or_invalid")
        regime_payload = self.storage.load_snapshot(self.config.regime_latest_path)
        synthetic_stage2 = {
            "stage": "intra_finder",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "status": "completed",
                "market_date": market_date,
                "universe_version": event.get("universe_version"),
            },
            "stocks": [event],
        }
        packet = self._build_candidate_packet(
            market_date=market_date,
            candidate_record=event,
            candidate_source="intra_finder_event",
            stage2_payload=synthetic_stage2,
            monitor_payload=None,
            regime_payload=regime_payload,
            regime_enabled=True,
            account_context=account_context,
        )
        packet.update(event)
        self._strip_monitor_context(packet)
        run_context = {
            "trade_session_id": f"intra-{event['event_id']}",
            "request_id": str(event["event_id"]),
        }
        results = self._run_stock_agents(
            [packet],
            trade_config or {},
            event_callback,
            run_context,
        )
        payload = {
            "stage": "stock_agent",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "status": "completed",
                "market_date": market_date,
                "candidate_source": "intra_finder_event",
                "event_id": event["event_id"],
                "selected_count": 1,
                "evaluated_count": len(results),
                "executed_count": sum(1 for item in results if self._is_placed_result(item)),
            },
            "results": results,
        }
        self._save_payload(payload)
        return payload

    def resolve_user_trade_config(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a manual amount or fetch current balance for automatic mode."""
        user_id = str(user.get("user_id") or "")
        mode = str(user.get("trade_mode") or ("manual" if user.get("trade_amount") not in (None, "") else "auto")).lower()
        if mode == "manual":
            amount = TradingAmountService.parse(user.get("trade_amount"))
            if amount is None:
                return {
                    "user_id": user_id,
                    "eligible": False,
                    "status_code": "manual_amount_invalid",
                    "message": "This account's manual amount is invalid. Save a positive amount or leave it blank for automatic sizing.",
                }
            return {"user_id": user_id, "eligible": True, "trade_mode": "manual", "amount_source": "user_amount", "trade_amount": amount}
        try:
            account_context = self._build_account_context()
            effective = self._with_effective_trade_amount({"trade_mode": "auto"}, account_context) or {}
            amount = TradingAmountService.parse(effective.get("trade_amount"))
        except Exception as exc:
            return {
                "user_id": user_id,
                "eligible": False,
                "status_code": "available_balance_unavailable",
                "message": "Automatic sizing is paused for this account because available broker balance could not be loaded.",
                "error": f"{type(exc).__name__}: {exc}",
            }
        if amount is None:
            return {
                "user_id": user_id,
                "eligible": False,
                "status_code": "available_balance_unavailable",
                "message": "Automatic sizing is paused for this account because available broker balance is missing or zero.",
            }
        return {"user_id": user_id, "eligible": True, "trade_mode": "auto", "amount_source": "available_balance", "trade_amount": amount}

    def prepare_user_event(self, event: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """Apply dynamic, user-specific Stage 2 eligibility without changing Stage 1."""
        user_id = str(user.get("user_id") or "")
        amount = TradingAmountService.parse(user.get("trade_amount"))
        price = self._reference_price(event)
        quantity = TradingAmountService.quantity(amount, price)
        base = {
            "user_id": user_id,
            "trade_mode": user.get("trade_mode"),
            "amount_source": user.get("amount_source"),
            "trade_amount": amount,
            "current_price": price,
        }
        if amount is None:
            return {**base, "eligible": False, "status_code": "amount_missing_or_invalid", "message": "Agent dispatch paused for this user because the trading amount is missing or invalid."}
        if price <= 0:
            return {**base, "eligible": False, "status_code": "price_unavailable", "message": "Agent dispatch paused for this user because the current stock price is unavailable."}
        if quantity < 1:
            return {**base, "eligible": False, "status_code": "price_above_trading_amount", "message": "This stock costs more than the user's trading amount, so no agent was started."}
        depth = event.get("five_level_depth") or []
        direction = str(event.get("direction") or "LONG").upper()
        slippage = TradingAmountService.estimated_slippage(depth, direction=direction if direction in {"LONG", "SHORT"} else "LONG", price=price, quantity=quantity)
        if slippage is None:
            return {**base, "requested_quantity": quantity, "eligible": False, "status_code": "user_depth_unavailable", "message": "Agent dispatch paused for this user because five-level depth cannot fill the requested quantity."}
        if slippage > self.config.intra_finder_max_slippage_percent:
            return {**base, "requested_quantity": quantity, "estimated_slippage_percent": slippage, "eligible": False, "status_code": "user_slippage_too_high", "message": "Agent dispatch paused for this user because estimated slippage is too high."}
        routed = dict(event)
        routed.update({
            "user_id": user_id,
            "trade_amount": amount,
            "trade_mode": user.get("trade_mode"),
            "amount_source": user.get("amount_source"),
            "requested_quantity": quantity,
            "user_estimated_notional": round(quantity * price, 2),
            "user_estimated_slippage_percent": slippage,
            "affordability": {"eligible": True, "price": price, "trade_amount": amount, "trade_mode": user.get("trade_mode"), "amount_source": user.get("amount_source"), "requested_quantity": quantity},
        })
        return {**base, "requested_quantity": quantity, "estimated_slippage_percent": slippage, "eligible": True, "status_code": "eligible", "event": routed}

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
            quantity = TradingAmountService.quantity(margin_budget, reference_price)
            enriched = dict(stock)
            enriched["manual_margin_filter"] = {
                "trade_amount": margin_budget,
                "reference_price": reference_price,
                "requested_quantity": quantity,
                "included": quantity >= 1,
            }
            if quantity >= 1:
                filtered.append(enriched)
        return filtered

    def _calculate_one_share_margin(self, stock: Dict[str, Any], side: str, reference_price: float) -> Dict[str, Any]:
        security_id = int(stock.get("security_id") or 0)
        try:
            response = self.execution_helper.dhan.calculate_margin_requirement(
                security_id=security_id,
                exchange_segment=str(stock.get("exchange_segment") or "").upper(),
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
        max_workers = min(
            max(1, len(candidate_packets)),
            max(1, int(self.config.stock_agent_max_workers)),
        )
        results: Dict[int, Dict[str, Any]] = {}
        failures: List[Dict[str, Any]] = []
        execution_coordinator = StockExecutionCoordinator()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(
                    self._run_single_stock_agent,
                    index,
                    packet,
                    trade_config,
                    event_callback,
                    run_context or {},
                    execution_coordinator,
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
        execution_coordinator: Optional[StockExecutionCoordinator] = None,
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
            days=25,
            interval=1,
            exchange_segment=str(candidate_packet.get("exchange_segment") or "").upper(),
            instrument_candidates=[candidate_packet.get("instrument"), "EQUITY"],
        )
        if not intraday_resp or str(intraday_resp.get("status", "")).lower() != "success":
            remarks = intraday_resp.get("remarks") if isinstance(intraday_resp, dict) else None
            if self.dhan.is_auth_invalid(intraday_resp):
                raise RuntimeError(f"stock_agent_auth_invalid::{remarks}")
            raise RuntimeError(f"stock_agent_intraday_history_failed::{security_id}::{remarks}")

        intraday_frame_fetched_at = self.market_time.now()
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
        if int(chart_bundle.get("chart_count") or 0) != 9:
            raise RuntimeError(
                f"stock_agent_chart_contract_incomplete::{security_id}::"
                f"{chart_bundle.get('chart_count')} charts"
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
        margin_budget = self._resolve_margin_budget(trade_config, candidate_packet)
        market_data_toolkit = StockMarketDataToolkit(
            dhan=isolated_dhan,
            market_time=self.market_time,
            security_id=security_id,
            symbol=str(candidate_packet.get("symbol") or ""),
            display_name=str(candidate_packet.get("display_name") or candidate_packet.get("symbol") or ""),
            stock_context=candidate_packet,
            instrument=candidate_packet.get("instrument"),
            intraday_frame=intraday_frame,
            intraday_frame_fetched_at=intraday_frame_fetched_at,
            exchange_segment=str(candidate_packet.get("exchange_segment") or "").upper(),
        )
        technical_toolkit = StockTechnicalToolkit(chart_bundle, market_time=self.market_time)
        account_toolkit = StockAccountToolkit(
            isolated_dhan,
            security_id=security_id,
            margin_budget=margin_budget,
        )
        execution_toolkit = StockExecutionToolkit(
            isolated_dhan,
            security_id=security_id,
            margin_budget=margin_budget,
            exchange_segment=str(candidate_packet.get("exchange_segment") or "").upper(),
            coordinator=execution_coordinator,
            amount_source=str(trade_config.get("amount_source") or "user_amount"),
        )
        research_toolkit = self._build_research_toolkit(candidate_packet)
        stock_toolkits = [
            market_data_toolkit,
            technical_toolkit,
            account_toolkit,
            execution_toolkit,
        ]
        if research_toolkit is not None:
            stock_toolkits.append(research_toolkit)
        agent = StockAgent(stock_toolkits)
        stock_packet = {
            "market_date": candidate_packet.get("market_date"),
            "timing_context": self._build_stock_agent_timing_context(candidate_packet),
            "selected_stock": {
                "security_id": selected_stock.get("security_id"),
                "symbol": selected_stock.get("symbol"),
                "display_name": selected_stock.get("display_name"),
                "trade_amount": trade_config.get("trade_amount"),
                "trade_mode": trade_config.get("trade_mode"),
                "amount_source": trade_config.get("amount_source"),
                "requested_quantity": candidate_packet.get("requested_quantity"),
                "estimated_notional": candidate_packet.get("user_estimated_notional"),
                "estimated_slippage_percent": candidate_packet.get("user_estimated_slippage_percent"),
            },
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
        timeline: List[Dict[str, Any]] = []
        sequence = 0

        def emit_agent_progress(progress: Dict[str, Any]) -> None:
            nonlocal sequence
            sequence += 1
            enriched = {
                **progress,
                "sequence": sequence,
                "rank": index + 1,
                "security_id": security_id,
                "symbol": candidate_packet.get("symbol"),
                "display_name": candidate_packet.get("display_name"),
            }
            timeline.append(enriched)
            self._emit(event_callback, enriched)

        emit_agent_progress(
            {
                "type": "stock_agent_input",
                "message": (
                    f"Analyze {candidate_packet.get('display_name') or candidate_packet.get('symbol')} "
                    "using the nine attached evidence charts and scoped tools."
                ),
                "input": stock_packet,
            }
        )
        report_text = agent.analyze(
            stock_packet,
            cloud_image_urls,
            run_context=agent_run_context,
            progress_callback=emit_agent_progress,
        )
        agent.last_run_metadata["timeline"] = timeline
        decision = execution_toolkit.decision_snapshot(
            str(candidate_packet.get("display_name") or candidate_packet.get("symbol") or "")
        )
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
            analytical_titles = {
                "volume_participation": "Volume and Participation",
                "momentum_volatility": "Momentum and Volatility",
                "price_structure_liquidity": "Price-Structure Liquidity",
                "tpo_profile": "TPO Market Profile",
            }
            title = analytical_titles.get(
                key,
                f"{str(info.get('day_type') or '').title()} {info.get('label') or ''}".strip(),
            )
            cards.append(
                {
                    "id": key,
                    "title": title,
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
        selected_stock = stock_packet.get("selected_stock") or {}
        lines = [
            f"# {display_name} Agent Instructions",
            "",
            "- Analyze the assigned stock for a sound intraday entry using the attached charts and available tools.",
            "- Focus only on the assigned stock.",
            "- Never modify, cancel, exit, hedge, convert, or otherwise touch another stock's position or order.",
            "- Any trade opened is for the current trading day only.",
            "- After the main analysis, call get_current_stock_state once and use its compact fresh quote and latest completed/partial candles before the final decision or order.",
            "- Return the analysis and outcome naturally and concisely.",
            "",
            "## Assignment",
            f"- Security ID: {selected_stock.get('security_id')}",
            f"- Stock: {selected_stock.get('display_name') or selected_stock.get('symbol')}",
        ]
        if selected_stock.get("symbol"):
            lines.append(f"- Symbol: {selected_stock.get('symbol')}")
        if selected_stock.get("trade_amount") is not None:
            lines.extend([
                f"- Strict cash/notional cap: Rs {selected_stock.get('trade_amount')}",
                f"- Sizing mode: {selected_stock.get('trade_mode')} ({selected_stock.get('amount_source')})",
                f"- Requested whole-share quantity: {selected_stock.get('requested_quantity')}",
                f"- Estimated notional: Rs {selected_stock.get('estimated_notional')}",
                f"- User-sized depth slippage estimate: {selected_stock.get('estimated_slippage_percent')}%",
                "- Do not assume leverage. Current LTP and affordability are revalidated immediately before placement.",
            ])
        return "\n".join(lines)

    def _build_data_markdown(self, display_name: str, stock_packet: Dict[str, Any]) -> str:
        timing = stock_packet.get("timing_context") or {}
        session = timing.get("market_session") or {}
        lines = [
            f"# {display_name} Agent Context",
            "",
            f"- Indian date and time: {timing.get('current_market_time_ist')}",
            f"- Regular market session: {session.get('regular_session') or '09:15-15:30 IST'}",
            f"- Market open now: {session.get('is_open_now')}",
            f"- Minutes to close: {session.get('minutes_to_close')}",
            "",
            "Detailed market, technical, account, and execution information is available to the agent through scoped tools.",
        ]
        return "\n".join(line for line in lines if not line.endswith(": None"))

    def _build_stock_agent_timing_context(self, candidate_packet: Dict[str, Any]) -> Dict[str, Any]:
        now = self.market_time.now()
        open_at = now.replace(
            hour=self.config.market_open_hour,
            minute=self.config.market_open_minute,
            second=0,
            microsecond=0,
        )
        close_at = now.replace(
            hour=self.config.market_close_hour,
            minute=self.config.market_close_minute,
            second=0,
            microsecond=0,
        )
        return {
            "current_market_time_ist": now.strftime("%d %B %Y, %H:%M:%S IST"),
            "market_session": {
                "regular_session": "09:15-15:30 IST",
                "is_open_now": bool(open_at <= now <= close_at),
                "minutes_to_close": max(0, int((close_at - now).total_seconds() // 60)),
            },
        }

    def _resolve_margin_budget(
        self,
        trade_config: Dict[str, Any],
        candidate_packet: Dict[str, Any],
    ) -> float:
        try:
            configured = float(trade_config.get("trade_amount") or 0)
        except Exception:
            configured = 0.0
        if configured > 0:
            return configured
        margin_filter = candidate_packet.get("manual_margin_filter") or {}
        try:
            return max(0.0, float(margin_filter.get("margin_budget") or 0))
        except Exception:
            return 0.0

    def _build_research_toolkit(self, candidate_packet: Dict[str, Any]) -> Any:
        try:
            from pipeline.stock.toolkits.research_toolkit import StockResearchToolkit

            return StockResearchToolkit(
                display_name=str(candidate_packet.get("display_name") or ""),
                symbol=str(candidate_packet.get("symbol") or ""),
                market_time=self.market_time,
            )
        except ImportError:
            return None

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

    @staticmethod
    def _is_placed_result(item: Dict[str, Any]) -> bool:
        return str((item.get("decision") or {}).get("execution_status") or "").strip().lower() in {
            "traded",
            "part_traded",
        }

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
