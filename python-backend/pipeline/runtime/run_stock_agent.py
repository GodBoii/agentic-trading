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
from pipeline.services.order_placement_gate import OrderPlacementGate
from pipeline.services.trading_amount_service import TradingAmountService
from pipeline.stock import StockAgent, StockDecisionContextBuilder
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
        self.order_placement_gate = OrderPlacementGate(
            self.dhan,
            self.config.order_placement_state_path,
        )

    def run_cycle(
        self,
        force: bool = False,
        trade_config: Optional[Dict[str, Any]] = None,
        use_regime_analysis: Optional[bool] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        run_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        gate = getattr(self, "order_placement_gate", None)
        if gate is not None and not gate.allowed:
            print("Dhan order placement is blocked. Stock agent is idling.")
            return None
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
        gate = getattr(self, "order_placement_gate", None)
        if gate is not None and not gate.allowed:
            raise RuntimeError("order_placement_blocked")
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            raise RuntimeError("ai_trading_disabled")
        market_date = self.market_time.market_date_str()
        if str(event.get("market_date") or "") != market_date:
            raise RuntimeError("stale_intra_finder_event")
        if str(event.get("exchange_segment") or "").upper() not in {"NSE_EQ", "BSE_EQ"}:
            raise RuntimeError("event_missing_valid_exchange_segment")

        account_context = self._build_account_context()
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise RuntimeError("user_id_required_for_agent_session")
        trade_config = dict(trade_config or {})
        trade_config["trade_mode"] = str(trade_config.get("trade_mode") or "auto").lower()
        trade_config["trade_amount"] = TradingAmountService.parse(trade_config.get("trade_amount"))
        trade_config["user_id"] = normalized_user_id
        if trade_config["trade_amount"] is None:
            raise RuntimeError("trading_amount_missing_or_invalid")
        regime_payload = None
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
            regime_enabled=False,
            account_context=account_context,
        )
        packet.update(event)
        self._strip_monitor_context(packet)
        run_context = {
            "trade_session_id": f"intra-{event['event_id']}",
            "request_id": str(event["event_id"]),
            "user_id": normalized_user_id,
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
            try:
                account_context = self._build_sizing_account_context()
                capacity = self._account_margin_capacity(account_context)
                available = self._account_available_balance(account_context)
            except Exception as exc:
                return {
                    "user_id": user_id,
                    "eligible": False,
                    "status_code": "available_balance_unavailable",
                    "message": "Fixed sizing is paused because account margin could not be loaded.",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            max_concurrent_trades = int(capacity // amount) if capacity > 0 else 0
            if max_concurrent_trades < 1:
                return {
                    "user_id": user_id,
                    "eligible": False,
                    "status_code": "manual_amount_exceeds_account_capacity",
                    "message": "The fixed margin allocation exceeds the account's current margin capacity.",
                    "trade_mode": "manual",
                    "trade_amount": amount,
                    "account_margin_capacity": capacity,
                }
            return {
                "user_id": user_id,
                "eligible": True,
                "trade_mode": "manual",
                "amount_source": "user_amount",
                "trade_amount": amount,
                "account_available_balance": available,
                "account_margin_capacity": capacity,
                "max_concurrent_trades": max_concurrent_trades,
            }
        try:
            account_context = self._build_sizing_account_context()
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
        return {
            "user_id": user_id,
            "eligible": True,
            "trade_mode": "auto",
            "amount_source": "available_balance",
            "trade_amount": amount,
            "account_available_balance": effective.get("account_available_balance"),
            "account_margin_capacity": effective.get("account_margin_capacity"),
            "max_concurrent_trades": int(self.config.stock_agent_max_concurrent_trades),
        }

    def _with_effective_trade_amount(
        self,
        trade_config: Optional[Dict[str, Any]],
        account_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        resolved = super()._with_effective_trade_amount(trade_config, account_context)
        if not resolved or str(resolved.get("trade_mode") or "auto").lower() != "auto":
            return resolved
        if (
            (trade_config or {}).get("trade_amount") not in (None, "")
            and str((trade_config or {}).get("amount_source") or "") == "available_balance"
        ):
            return resolved
        copied = dict(resolved)
        available = self._account_available_balance(account_context)
        capacity = self._account_margin_capacity(account_context)
        slots = max(1, int(self.config.stock_agent_max_concurrent_trades))
        copied["trade_amount"] = (
            int((capacity * 100) // slots) / 100.0
            if capacity > 0
            else None
        )
        copied["account_available_balance"] = available
        copied["account_margin_capacity"] = capacity
        copied["margin_slot_count"] = slots
        return copied

    def _build_sizing_account_context(self) -> Dict[str, Any]:
        fund_limits = self.dhan.fetch_fund_limits()
        raw_data = fund_limits.get("data") if isinstance(fund_limits, dict) else {}
        if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict):
            raw_data = raw_data["data"]
        return {
            "funds": {
                "status": fund_limits.get("status") if isinstance(fund_limits, dict) else "failure",
                "data": raw_data if isinstance(raw_data, dict) else {},
            }
        }

    @staticmethod
    def _account_fund_data(account_context: Dict[str, Any]) -> Dict[str, Any]:
        funds = (account_context.get("funds") or {}).get("data") or {}
        if isinstance(funds, dict) and isinstance(funds.get("data"), dict):
            funds = funds["data"]
        return funds if isinstance(funds, dict) else {}

    @classmethod
    def _account_available_balance(cls, account_context: Dict[str, Any]) -> float:
        funds = cls._account_fund_data(account_context)
        for key in ("availabelBalance", "availableBalance", "withdrawableBalance"):
            try:
                value = float(funds.get(key) or 0.0)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return 0.0

    @classmethod
    def _account_margin_capacity(cls, account_context: Dict[str, Any]) -> float:
        funds = cls._account_fund_data(account_context)
        available = cls._account_available_balance(account_context)
        try:
            utilized = max(0.0, float(funds.get("utilizedAmount") or 0.0))
        except (TypeError, ValueError):
            utilized = 0.0
        try:
            start_of_day = max(0.0, float(funds.get("sodLimit") or 0.0))
        except (TypeError, ValueError):
            start_of_day = 0.0
        return max(available, available + utilized, start_of_day)

    def prepare_user_event(self, event: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """Apply dynamic, user-specific Stage 2 eligibility without changing Stage 1."""
        user_id = str(user.get("user_id") or "")
        amount = TradingAmountService.parse(user.get("trade_amount"))
        price = self._reference_price(event)
        direction = str(event.get("direction") or "LONG").upper()
        side = "SELL" if direction == "SHORT" else "BUY"
        margin_check = (
            self._calculate_one_share_margin(event, side, price)
            if amount is not None and price > 0
            else {"status": "failure", "total_margin": None}
        )
        margin_per_share = margin_check.get("total_margin")
        quantity = 0
        if amount is not None and price > 0 and margin_per_share:
            quantity = min(
                int(float(amount) // float(margin_per_share)),
                int((float(amount) * float(self.config.stock_agent_max_leverage)) // price),
            )
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
            return {**base, "eligible": False, "status_code": "margin_allocation_too_small", "message": "The assigned margin slot cannot support one share at Dhan's current margin."}
        depth = event.get("five_level_depth") or []
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
            "margin_per_share": margin_per_share,
            "user_estimated_notional": round(quantity * price, 2),
            "user_estimated_slippage_percent": slippage,
            "affordability": {"eligible": True, "price": price, "margin_allocation": amount, "margin_per_share": margin_per_share, "trade_mode": user.get("trade_mode"), "amount_source": user.get("amount_source"), "requested_quantity": quantity},
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
        packet.pop("regime_report", None)
        packet.pop("latest_regime_context", None)
        packet["regime_analysis_enabled"] = False
        snapshots = packet.get("source_snapshots")
        if isinstance(snapshots, dict):
            snapshots.pop("monitor_generated_at_utc", None)
            snapshots.pop("monitor_generated_at_ist", None)
            snapshots.pop("regime_generated_at_utc", None)
            snapshots.pop("regime_generated_at_ist", None)
            snapshots["regime_analysis_enabled"] = False
        timing = packet.get("timing_context")
        if isinstance(timing, dict):
            source_times = timing.get("source_snapshot_times")
            if isinstance(source_times, dict):
                source_times.pop("monitor_generated_at_utc", None)
                source_times.pop("monitor_generated_at_ist", None)
                source_times.pop("regime_generated_at_utc", None)
                source_times.pop("regime_generated_at_ist", None)
            source_ages = timing.get("source_snapshot_ages_seconds")
            if isinstance(source_ages, dict):
                source_ages.pop("monitor", None)
                source_ages.pop("regime", None)

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
            quantity = int(
                (margin_budget * float(self.config.stock_agent_max_leverage))
                // reference_price
            )
            enriched = dict(stock)
            enriched["manual_margin_filter"] = {
                "trade_amount": margin_budget,
                "max_leverage": float(self.config.stock_agent_max_leverage),
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
        execution_coordinator = StockExecutionCoordinator(
            order_placement_gate=self.order_placement_gate,
        )

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
        gate = getattr(self, "order_placement_gate", None)
        if gate is not None and not gate.allowed:
            raise RuntimeError("order_placement_blocked")
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
        exchange_segment = str(candidate_packet.get("exchange_segment") or "").upper()
        recent_bars = candidate_packet.get("chart_seed_bars") or []
        intraday_frame = self.signal_cache.load_frame(
            market_date=str(candidate_packet["market_date"]),
            exchange_segment=exchange_segment,
            security_id=security_id,
            recent_bars=recent_bars,
        )
        # Full-session seed bars are chart transport, not model or session evidence.
        candidate_packet.pop("chart_seed_bars", None)
        cache_used = intraday_frame is not None and not intraday_frame.empty
        if not cache_used:
            intraday_resp = self.dhan.fetch_intraday_history(
                security_id,
                days=25,
                interval=1,
                exchange_segment=exchange_segment,
                instrument_candidates=[candidate_packet.get("instrument"), "EQUITY"],
            )
            if not intraday_resp or str(intraday_resp.get("status", "")).lower() != "success":
                remarks = intraday_resp.get("remarks") if isinstance(intraday_resp, dict) else None
                if self.dhan.is_auth_invalid(intraday_resp):
                    raise RuntimeError(f"stock_agent_auth_invalid::{remarks}")
                raise RuntimeError(f"stock_agent_intraday_history_failed::{security_id}::{remarks}")
            intraday_frame = self.dhan.intraday_response_to_df(intraday_resp)
            intraday_frame = self.signal_cache.merge_recent_bars(intraday_frame, recent_bars)

        intraday_frame_fetched_at = self.market_time.now()
        artifact_identity = self._slugify(
            candidate_packet.get("event_id")
            or (run_context or {}).get("request_id")
            or f"manual-{int(time.time() * 1000)}"
        )
        artifacts_dir = (
            self.config.stock_analyzer_artifacts_dir
            / candidate_packet["market_date"]
            / self._slugify(candidate_packet["display_name"])
            / artifact_identity
        )

        selected_stock = self.execution_helper._normalize_selected_stock(
            {"rank": index + 1, "candidate": candidate_packet}
        )
        isolated_dhan = DhanService(self.config, prefer_gateway=False)
        margin_budget = self._resolve_margin_budget(trade_config, candidate_packet)
        market_data_toolkit = StockMarketDataToolkit(
            dhan=self.dhan,
            market_time=self.market_time,
            security_id=security_id,
            symbol=str(candidate_packet.get("symbol") or ""),
            display_name=str(candidate_packet.get("display_name") or candidate_packet.get("symbol") or ""),
            stock_context=candidate_packet,
            instrument=candidate_packet.get("instrument"),
            intraday_frame=intraday_frame,
            intraday_frame_fetched_at=intraday_frame_fetched_at,
            exchange_segment=exchange_segment,
        )
        account_toolkit = StockAccountToolkit(
            isolated_dhan,
            security_id=security_id,
            margin_budget=margin_budget,
        )
        context_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="stock-context")
        context_futures = {
            "security_overview": context_executor.submit(
                self._safe_initial_context_component,
                "security_overview",
                market_data_toolkit.security_overview_payload,
            ),
            "current_stock_state": context_executor.submit(
                self._safe_initial_context_component,
                "current_stock_state",
                market_data_toolkit.current_stock_state_payload,
            ),
            "account_overview": context_executor.submit(
                self._safe_initial_context_component,
                "account_overview",
                account_toolkit.account_overview_payload,
            ),
        }
        try:
            chart_bundle = self.charting.build_intraday_chart_set(
                frame=intraday_frame,
                display_name=candidate_packet["display_name"],
                market_date=candidate_packet["market_date"],
                output_dir=artifacts_dir,
                signal_time_ist=candidate_packet.get("created_at"),
            )
            security_overview = context_futures["security_overview"].result()
            current_stock_state = context_futures["current_stock_state"].result()
            account_overview = context_futures["account_overview"].result()
        finally:
            context_executor.shutdown(wait=True, cancel_futures=True)
        chart_bundle["history_cache_used"] = cache_used
        if int(chart_bundle.get("chart_count") or 0) != 8:
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

        technical_toolkit = StockTechnicalToolkit(chart_bundle, market_time=self.market_time)
        execution_toolkit = StockExecutionToolkit(
            isolated_dhan,
            security_id=security_id,
            margin_budget=margin_budget,
            exchange_segment=str(candidate_packet.get("exchange_segment") or "").upper(),
            coordinator=execution_coordinator,
            amount_source=str(trade_config.get("amount_source") or "user_amount"),
            max_leverage=float(self.config.stock_agent_max_leverage),
            max_risk_fraction_per_slot=float(
                self.config.stock_agent_max_risk_fraction_per_slot
            ),
            max_concurrent_trades=int(
                trade_config.get("max_concurrent_trades")
                or self.config.stock_agent_max_concurrent_trades
            ),
            final_state_loader=market_data_toolkit.current_stock_state_payload,
            final_quote_max_age_seconds=float(self.config.stock_agent_final_quote_max_age_seconds),
            final_candle_max_age_seconds=float(self.config.stock_agent_final_candle_max_age_seconds),
            max_entry_drift_risk_fraction=float(
                self.config.stock_agent_max_entry_drift_risk_fraction
            ),
        )
        selected_stock_context = {
            "security_id": selected_stock.get("security_id"),
            "symbol": selected_stock.get("symbol"),
            "display_name": selected_stock.get("display_name"),
            "trade_amount": trade_config.get("trade_amount"),
            "trade_mode": trade_config.get("trade_mode"),
            "amount_source": trade_config.get("amount_source"),
            "requested_quantity": candidate_packet.get("requested_quantity"),
            "estimated_notional": candidate_packet.get("user_estimated_notional"),
            "estimated_slippage_percent": candidate_packet.get("user_estimated_slippage_percent"),
        }
        timing_context = self._build_stock_agent_timing_context(candidate_packet)
        decision_context = StockDecisionContextBuilder.build(
            selected_stock=selected_stock_context,
            timing_context=timing_context,
            security_overview=security_overview,
            current_state=current_stock_state,
            technical_data=self._safe_initial_context_component(
                "technical_data",
                technical_toolkit.technical_data_payload,
            ),
            account_overview=account_overview,
        )
        # The LLM receives exactly two functions. All read-only evidence is supplied once above.
        agent = StockAgent([execution_toolkit])
        stock_packet = {
            "market_date": candidate_packet.get("market_date"),
            "decision_context": decision_context,
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
                    "using the eight attached evidence charts, the initial decision snapshot, "
                    "and the two protected-execution tools."
                ),
                "input": stock_packet,
            }
        )
        gate = getattr(self, "order_placement_gate", None)
        if gate is not None and not gate.allowed:
            raise RuntimeError("order_placement_blocked_before_agent")
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
        def upload_one(chart_path: str) -> tuple[str, Dict[str, Any]]:
            filename = Path(str(chart_path)).name
            storage_path = (
                f"{trade_session_id}/agents/{rank}-{agent_slug}/images/{filename}"
            )
            uploaded = CloudPersistenceService.upload_image(chart_path, storage_path)
            return str(chart_path), uploaded

        workers = min(4, max(1, len(chart_paths)))
        uploaded_by_path: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="chart-upload") as executor:
            future_by_path = {
                executor.submit(upload_one, str(chart_path)): str(chart_path)
                for chart_path in chart_paths
            }
            for future in as_completed(future_by_path):
                chart_path, uploaded = future.result()
                uploaded_by_path[chart_path] = uploaded

        cloud_urls: List[str] = []
        for chart_path in chart_paths:
            uploaded = uploaded_by_path[str(chart_path)]
            cloud_urls.append(str(uploaded["cloud_url"]))
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
        decision_context = stock_packet.get("decision_context") or {}
        instrument = decision_context.get("instrument") or {}
        risk_budget = decision_context.get("risk_budget") or {}
        lines = [
            f"# {display_name} Agent Instructions",
            "",
            "- Analyze the assigned stock using the attached charts and the supplied initial decision snapshot.",
            "- Focus only on the assigned stock.",
            "- Never modify, cancel, exit, hedge, convert, or otherwise touch another stock's position or order.",
            "- Any trade opened is for the current trading day only.",
            "- The only tools are estimate_intraday_quantity and place_protected_intraday_order.",
            "- Size with estimate_intraday_quantity before placing a protected order.",
            "- Return the analysis and outcome naturally and concisely.",
            "",
            "## Assignment",
            f"- Security ID: {instrument.get('security_id')}",
            f"- Stock: {instrument.get('display_name') or instrument.get('symbol')}",
        ]
        if instrument.get("symbol"):
            lines.append(f"- Symbol: {instrument.get('symbol')}")
        if risk_budget.get("margin_allocation_rupees") is not None:
            lines.extend([
                f"- Margin allocation: Rs {risk_budget.get('margin_allocation_rupees')}",
                f"- Maximum leverage: {self.config.stock_agent_max_leverage:.2f}x, further limited by Dhan's current margin response.",
                "- Current balance, LTP, setup freshness, and margin are revalidated immediately before placement.",
            ])
        return "\n".join(lines)

    def _build_data_markdown(self, display_name: str, stock_packet: Dict[str, Any]) -> str:
        from pipeline.stock.toolkits.markdown_result import tool_result_markdown

        rendered = tool_result_markdown(stock_packet.get("decision_context") or {})
        return rendered.replace("## Tool result", f"# {display_name} Initial Decision Snapshot", 1)

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

    @staticmethod
    def _safe_initial_context_component(
        name: str,
        loader: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            payload = loader()
            return payload if isinstance(payload, dict) else {
                "status": "error",
                "errors": [f"{name}:invalid_payload"],
            }
        except Exception as exc:
            return {
                "status": "error",
                "errors": [f"{name}:{type(exc).__name__}:{exc}"],
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
