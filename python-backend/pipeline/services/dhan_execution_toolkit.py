from __future__ import annotations

import json
import os
import re
import uuid
from hashlib import sha256
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit

from pipeline.services.dhan_service import DhanService


class DhanExecutionToolkit(Toolkit):
    def __init__(self, dhan_service: DhanService, entry_only: bool = False):
        entry_tools = [
            self.get_account_snapshot,
            self.get_order_book,
            self.get_order_by_id,
            self.get_order_by_correlation_id,
            self.get_trade_book,
            self.calculate_margin_requirement,
            self.calculate_multi_order_margin,
            self.calculate_equity_order_quantity,
            self.calculate_intraday_equity_order_quantity,
            self.place_intraday_equity_order,
            self.place_protected_intraday_super_order,
            self.get_super_order_list,
            self.get_kill_switch_status,
            self.get_pnl_exit,
        ]
        all_tools = [
            *entry_tools,
            self.modify_super_order,
            self.cancel_super_order,
            self.convert_position,
            self.place_forever_order,
            self.modify_forever_order,
            self.cancel_forever_order,
            self.get_forever_order_list,
            self.place_conditional_trigger,
            self.modify_conditional_trigger,
            self.delete_conditional_trigger,
            self.get_conditional_trigger_by_id,
            self.get_all_conditional_triggers,
            self.exit_position,
            self.exit_all_intraday_positions,
            self.activate_kill_switch,
            self.deactivate_kill_switch,
            self.configure_pnl_exit,
            self.disable_pnl_exit,
            self.generate_edis_tpin,
            self.get_edis_form,
            self.check_edis_status,
            self.get_ledger_report,
            self.get_trade_history,
            self.get_static_ips,
            self.set_static_ip,
            self.modify_static_ip,
            self.modify_order,
            self.cancel_order,
        ]
        super().__init__(
            name="dhan_execution_tools",
            tools=entry_tools if entry_only else all_tools,
        )
        self.dhan = dhan_service
        self.allow_live_orders = os.getenv("EXECUTIONER_ALLOW_LIVE_ORDERS", "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        self.default_risk_fraction = self._env_float("EXECUTIONER_RISK_FRACTION", 0.01)
        self.max_allocation_fraction = self._env_float("EXECUTIONER_MAX_ALLOCATION_FRACTION", 0.25)
        self.default_exchange_segment = os.getenv("EXECUTIONER_DEFAULT_EXCHANGE_SEGMENT", "BSE_EQ")
        self.allowed_security_id: Optional[int] = None

    def set_allowed_security_id(self, security_id: Optional[int]) -> None:
        self.allowed_security_id = int(security_id) if security_id else None

    def get_account_snapshot(self) -> str:
        payload = {
            "holdings": self.dhan.fetch_holdings(),
            "positions": self.dhan.fetch_positions(),
            "funds": self.dhan.fetch_fund_limits(),
        }
        return json.dumps(payload, ensure_ascii=True)

    def get_order_book(self) -> str:
        return json.dumps(self.dhan.fetch_order_book(), ensure_ascii=True)

    def get_order_by_id(self, order_id: str) -> str:
        return json.dumps(self.dhan.fetch_order_by_id(order_id), ensure_ascii=True)

    def get_order_by_correlation_id(self, correlation_id: str) -> str:
        return json.dumps(self.dhan.fetch_order_by_correlation_id(correlation_id), ensure_ascii=True)

    def get_trade_book(self, order_id: Optional[str] = None) -> str:
        return json.dumps(self.dhan.fetch_trade_book(order_id), ensure_ascii=True)

    def calculate_equity_order_quantity(
        self,
        reference_price: float,
        stop_loss_price: float,
        available_balance: float,
        risk_fraction: Optional[float] = None,
        max_allocation_fraction: Optional[float] = None,
    ) -> str:
        entry = max(0.0, float(reference_price))
        stop = max(0.0, float(stop_loss_price))
        balance = max(0.0, float(available_balance))
        per_share_risk = abs(entry - stop)

        risk_capital = balance * max(0.0, float(risk_fraction or self.default_risk_fraction))
        allocation_capital = balance * max(0.0, float(max_allocation_fraction or self.max_allocation_fraction))

        qty_by_allocation = int(allocation_capital // entry) if entry > 0 else 0
        qty_by_risk = int(risk_capital // per_share_risk) if per_share_risk > 0 else qty_by_allocation
        recommended_qty = max(0, min(qty_by_allocation, qty_by_risk))

        return json.dumps(
            {
                "reference_price": entry,
                "stop_loss_price": stop,
                "available_balance": balance,
                "per_share_risk": per_share_risk,
                "risk_capital": risk_capital,
                "allocation_capital": allocation_capital,
                "recommended_quantity": recommended_qty,
            },
            ensure_ascii=True,
        )

    def calculate_margin_requirement(
        self,
        security_id: int,
        side: str,
        quantity: int,
        reference_price: float,
        product_type: str = "INTRADAY",
        exchange_segment: str = "BSE_EQ",
        trigger_price: float = 0.0,
    ) -> str:
        validation_error = self._validate_order_inputs(side, quantity)
        if validation_error:
            return validation_error
        normalized_exchange_segment = self._normalize_exchange_segment(exchange_segment, int(security_id))
        return json.dumps(
            self.dhan.calculate_margin_requirement(
                security_id=int(security_id),
                exchange_segment=normalized_exchange_segment,
                transaction_type=str(side).strip().upper(),
                quantity=int(quantity),
                product_type=str(product_type).strip().upper(),
                price=float(reference_price),
                trigger_price=float(trigger_price),
            ),
            ensure_ascii=True,
        )

    def calculate_intraday_equity_order_quantity(
        self,
        security_id: int,
        side: str,
        reference_price: float,
        margin_budget: float,
        stop_loss_price: Optional[float] = None,
        max_risk_rupees: Optional[float] = None,
        max_quantity: Optional[int] = None,
        product_type: str = "INTRADAY",
        exchange_segment: str = "BSE_EQ",
        trigger_price: float = 0.0,
    ) -> str:
        """Size an intraday equity order from Dhan's margin for one share.

        Manual trade amount is treated as an intraday margin budget, not as a
        notional cap. The final order still needs a margin check for the chosen
        quantity immediately before placement.
        """
        normalized_side = str(side).strip().upper()
        budget = max(0.0, float(margin_budget))
        entry = max(0.0, float(reference_price))
        stop = float(stop_loss_price) if stop_loss_price is not None else None
        normalized_exchange_segment = self._normalize_exchange_segment(exchange_segment, int(security_id))

        validation_error = self._validate_order_inputs(normalized_side, 1)
        if validation_error:
            return validation_error
        if budget <= 0 or entry <= 0:
            return json.dumps(
                {
                    "status": "failure",
                    "remarks": "invalid_budget_or_reference_price",
                    "margin_budget": budget,
                    "reference_price": entry,
                },
                ensure_ascii=True,
            )

        one_share_margin = self.dhan.calculate_margin_requirement(
            security_id=int(security_id),
            exchange_segment=normalized_exchange_segment,
            transaction_type=normalized_side,
            quantity=1,
            product_type=str(product_type).strip().upper(),
            price=entry,
            trigger_price=float(trigger_price),
        )
        margin_data = one_share_margin.get("data") if isinstance(one_share_margin.get("data"), dict) else one_share_margin
        try:
            margin_per_share = float(margin_data.get("totalMargin"))
        except Exception:
            margin_per_share = 0.0
        if margin_per_share <= 0:
            return json.dumps(
                {
                    "status": "failure",
                    "remarks": "invalid_margin_per_share",
                    "margin_response": one_share_margin,
                },
                ensure_ascii=True,
            )

        qty_by_margin = int(budget // margin_per_share)
        qty_by_risk: Optional[int] = None
        per_share_risk: Optional[float] = None
        if stop is not None and max_risk_rupees is not None and float(max_risk_rupees) > 0:
            per_share_risk = abs(entry - stop)
            qty_by_risk = int(float(max_risk_rupees) // per_share_risk) if per_share_risk > 0 else qty_by_margin

        caps = [qty_by_margin]
        if qty_by_risk is not None:
            caps.append(qty_by_risk)
        if max_quantity is not None and int(max_quantity) > 0:
            caps.append(int(max_quantity))
        recommended_qty = max(0, min(caps))

        return json.dumps(
            {
                "status": "success",
                "security_id": int(security_id),
                "side": normalized_side,
                "exchange_segment": normalized_exchange_segment,
                "product_type": str(product_type).strip().upper(),
                "reference_price": entry,
                "stop_loss_price": stop,
                "margin_budget": budget,
                "margin_per_share": margin_per_share,
                "max_qty_by_margin": qty_by_margin,
                "max_risk_rupees": float(max_risk_rupees) if max_risk_rupees is not None else None,
                "per_share_risk": per_share_risk,
                "max_qty_by_risk": qty_by_risk,
                "max_quantity": int(max_quantity) if max_quantity is not None else None,
                "recommended_quantity": recommended_qty,
                "estimated_margin_required": round(recommended_qty * margin_per_share, 4),
                "estimated_notional": round(recommended_qty * entry, 4),
                "one_share_margin_response": one_share_margin,
            },
            ensure_ascii=True,
        )

    def calculate_multi_order_margin(
        self,
        scripts_json: str,
        include_position: bool = True,
        include_orders: bool = True,
    ) -> str:
        try:
            scripts = json.loads(scripts_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"status": "failure", "remarks": f"invalid_json: {exc}"}, ensure_ascii=True)
        if not isinstance(scripts, list) or not all(isinstance(item, dict) for item in scripts):
            return json.dumps({"status": "failure", "remarks": "scripts_json_must_be_array_of_objects"}, ensure_ascii=True)
        normalized_scripts = []
        for item in scripts:
            copied = dict(item)
            copied["exchangeSegment"] = self._normalize_exchange_segment(
                str(copied.get("exchangeSegment") or self.default_exchange_segment),
                int(copied.get("securityId", 0) or 0),
            )
            normalized_scripts.append(copied)
        return json.dumps(
            self.dhan.calculate_multi_order_margin(
                scripts=normalized_scripts,
                include_position=bool(include_position),
                include_orders=bool(include_orders),
            ),
            ensure_ascii=True,
        )

    def place_intraday_equity_order(
        self,
        security_id: int,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0,
        trigger_price: float = 0.0,
        validity: str = "DAY",
        exchange_segment: str = "BSE_EQ",
        disclosed_quantity: int = 0,
        correlation_id: Optional[str] = None,
        should_slice: bool = False,
        product_type: str = "INTRADAY",
        after_market_order: bool = False,
        amo_time: str = "OPEN",
    ) -> str:
        if not self.allow_live_orders:
            return json.dumps(
                {
                    "status": "blocked",
                    "remarks": "live_order_placement_disabled",
                },
                ensure_ascii=True,
            )

        scope_error = self._validate_selected_security_scope(int(security_id))
        if scope_error:
            return scope_error
        overlap_error = self._validate_no_selected_stock_overlap(int(security_id))
        if overlap_error:
            return overlap_error

        normalized_side = str(side).strip().upper()
        normalized_order_type = self._normalize_order_type(order_type)
        normalized_product_type = str(product_type).strip().upper()
        normalized_exchange_segment = self._normalize_exchange_segment(exchange_segment, int(security_id))
        if normalized_side not in {"BUY", "SELL"}:
            return json.dumps({"status": "failure", "remarks": "invalid_side"}, ensure_ascii=True)
        if int(quantity) <= 0:
            return json.dumps({"status": "failure", "remarks": "invalid_quantity"}, ensure_ascii=True)
        if normalized_product_type not in {"INTRADAY", "CNC", "MARGIN", "MTF", "CO", "BO"}:
            return json.dumps({"status": "failure", "remarks": "invalid_product_type"}, ensure_ascii=True)

        tag = self._normalize_correlation_id(correlation_id, prefix="exec")
        order_kwargs = dict(
            security_id=int(security_id),
            exchange_segment=normalized_exchange_segment,
            transaction_type=normalized_side,
            quantity=int(quantity),
            order_type=normalized_order_type,
            product_type=normalized_product_type,
            price=float(price),
            trigger_price=float(trigger_price),
            disclosed_quantity=int(disclosed_quantity),
            after_market_order=bool(after_market_order),
            amo_time=str(amo_time).strip().upper(),
            validity=validity,
            correlation_id=tag,
        )
        if should_slice:
            response = self.dhan.place_slice_order(**order_kwargs)
        else:
            response = self.dhan.place_order(**order_kwargs, should_slice=False)
        payload = {"correlation_id": tag}
        payload.update(response)
        return json.dumps(payload, ensure_ascii=True)

    def place_protected_intraday_super_order(
        self,
        security_id: int,
        side: str,
        quantity: int,
        entry_price: float,
        target_price: float,
        stop_loss_price: float,
        order_type: str = "LIMIT",
        trailing_jump: float = 0.0,
        exchange_segment: str = "BSE_EQ",
        product_type: str = "INTRADAY",
        correlation_id: Optional[str] = None,
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_super_order_placement_disabled")
        scope_error = self._validate_selected_security_scope(int(security_id))
        if scope_error:
            return scope_error
        overlap_error = self._validate_no_selected_stock_overlap(int(security_id))
        if overlap_error:
            return overlap_error
        validation_error = self._validate_order_inputs(side, quantity)
        if validation_error:
            return validation_error

        normalized_side = str(side).strip().upper()
        normalized_product_type = str(product_type).strip().upper()
        normalized_exchange_segment = self._normalize_exchange_segment(exchange_segment, int(security_id))
        entry = float(entry_price)
        target = float(target_price)
        stop = float(stop_loss_price)
        if normalized_side == "BUY" and not (stop < entry < target):
            return json.dumps({"status": "failure", "remarks": "buy_super_order_requires_stop_below_entry_and_target_above_entry"}, ensure_ascii=True)
        if normalized_side == "SELL" and not (target < entry < stop):
            return json.dumps({"status": "failure", "remarks": "sell_super_order_requires_target_below_entry_and_stop_above_entry"}, ensure_ascii=True)
        if normalized_product_type not in {"INTRADAY", "CNC", "MARGIN", "MTF"}:
            return json.dumps({"status": "failure", "remarks": "invalid_product_type"}, ensure_ascii=True)

        tag = self._normalize_correlation_id(correlation_id, prefix="exec-so")
        response = self.dhan.place_super_order(
            security_id=int(security_id),
            exchange_segment=normalized_exchange_segment,
            transaction_type=normalized_side,
            quantity=int(quantity),
            order_type=self._normalize_order_type(order_type, allowed={"LIMIT", "MARKET"}),
            product_type=normalized_product_type,
            price=entry,
            target_price=target,
            stop_loss_price=stop,
            trailing_jump=float(trailing_jump),
            correlation_id=tag,
        )
        payload = {"correlation_id": tag}
        payload.update(response)
        return json.dumps(payload, ensure_ascii=True)

    def get_super_order_list(self) -> str:
        return json.dumps(self.dhan.fetch_super_orders(), ensure_ascii=True)

    def modify_super_order(
        self,
        order_id: str,
        leg_name: str,
        order_type: Optional[str] = None,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        target_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        trailing_jump: Optional[float] = None,
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_super_order_modification_disabled")
        return json.dumps(
            self.dhan.modify_super_order(
                order_id=order_id,
                leg_name=str(leg_name).strip().upper(),
                order_type=self._normalize_order_type(order_type) if order_type else None,
                quantity=quantity,
                price=price,
                target_price=target_price,
                stop_loss_price=stop_loss_price,
                trailing_jump=trailing_jump,
            ),
            ensure_ascii=True,
        )

    def cancel_super_order(self, order_id: str, order_leg: str = "ENTRY_LEG") -> str:
        if not self.allow_live_orders:
            return self._blocked("live_super_order_cancellation_disabled")
        return json.dumps(self.dhan.cancel_super_order(order_id, str(order_leg).strip().upper()), ensure_ascii=True)

    def convert_position(
        self,
        security_id: int,
        convert_qty: int,
        from_product_type: str = "INTRADAY",
        to_product_type: str = "CNC",
        position_type: str = "LONG",
        exchange_segment: str = "BSE_EQ",
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_position_conversion_disabled")
        return json.dumps(
            self.dhan.convert_position(
                from_product_type=str(from_product_type).strip().upper(),
                exchange_segment=self._normalize_exchange_segment(exchange_segment, int(security_id)),
                position_type=str(position_type).strip().upper(),
                security_id=int(security_id),
                convert_qty=int(convert_qty),
                to_product_type=str(to_product_type).strip().upper(),
            ),
            ensure_ascii=True,
        )

    def place_forever_order(
        self,
        security_id: int,
        side: str,
        quantity: int,
        price: float,
        trigger_price: float,
        order_flag: str = "SINGLE",
        order_type: str = "LIMIT",
        product_type: str = "CNC",
        validity: str = "DAY",
        exchange_segment: str = "BSE_EQ",
        disclosed_quantity: int = 0,
        price1: Optional[float] = None,
        trigger_price1: Optional[float] = None,
        quantity1: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_forever_order_placement_disabled")
        validation_error = self._validate_order_inputs(side, quantity)
        if validation_error:
            return validation_error
        normalized_product_type = str(product_type).strip().upper()
        if normalized_product_type not in {"CNC", "MTF"}:
            return json.dumps(
                {
                    "status": "failure",
                    "remarks": "invalid_forever_product_type",
                    "allowed": ["CNC", "MTF"],
                },
                ensure_ascii=True,
            )
        tag = self._normalize_correlation_id(correlation_id, prefix="exec-fo")
        response = self.dhan.place_forever_order(
            security_id=int(security_id),
            exchange_segment=self._normalize_exchange_segment(exchange_segment, int(security_id)),
            transaction_type=str(side).strip().upper(),
            quantity=int(quantity),
            order_flag=str(order_flag).strip().upper(),
            order_type=self._normalize_order_type(order_type),
            product_type=normalized_product_type,
            price=float(price),
            trigger_price=float(trigger_price),
            validity=validity,
            disclosed_quantity=int(disclosed_quantity),
            price1=price1,
            trigger_price1=trigger_price1,
            quantity1=quantity1,
            correlation_id=tag,
        )
        payload = {"correlation_id": tag}
        payload.update(response)
        return json.dumps(payload, ensure_ascii=True)

    def modify_forever_order(
        self,
        order_id: str,
        quantity: int,
        price: float,
        trigger_price: float,
        order_flag: str = "SINGLE",
        leg_name: str = "TARGET_LEG",
        order_type: str = "LIMIT",
        validity: str = "DAY",
        disclosed_quantity: int = 0,
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_forever_order_modification_disabled")
        return json.dumps(
            self.dhan.modify_forever_order(
                order_id=order_id,
                order_flag=str(order_flag).strip().upper(),
                leg_name=str(leg_name).strip().upper(),
                order_type=self._normalize_order_type(order_type),
                quantity=int(quantity),
                price=float(price),
                trigger_price=float(trigger_price),
                validity=validity,
                disclosed_quantity=int(disclosed_quantity),
            ),
            ensure_ascii=True,
        )

    def cancel_forever_order(self, order_id: str) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_forever_order_cancellation_disabled")
        return json.dumps(self.dhan.cancel_forever_order(order_id), ensure_ascii=True)

    def get_forever_order_list(self) -> str:
        return json.dumps(self.dhan.fetch_forever_orders(), ensure_ascii=True)

    def place_conditional_trigger(self, condition_json: str, orders_json: str) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_conditional_trigger_placement_disabled")
        condition, orders, error = self._parse_condition_payload(condition_json, orders_json)
        if error:
            return error
        return json.dumps(self.dhan.place_conditional_trigger(condition=condition, orders=orders), ensure_ascii=True)

    def modify_conditional_trigger(self, alert_id: str, condition_json: str, orders_json: str) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_conditional_trigger_modification_disabled")
        condition, orders, error = self._parse_condition_payload(condition_json, orders_json)
        if error:
            return error
        return json.dumps(
            self.dhan.modify_conditional_trigger(alert_id=alert_id, condition=condition, orders=orders),
            ensure_ascii=True,
        )

    def delete_conditional_trigger(self, alert_id: str) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_conditional_trigger_deletion_disabled")
        return json.dumps(self.dhan.delete_conditional_trigger(alert_id), ensure_ascii=True)

    def get_conditional_trigger_by_id(self, alert_id: str) -> str:
        return json.dumps(self.dhan.fetch_conditional_trigger(alert_id), ensure_ascii=True)

    def get_all_conditional_triggers(self) -> str:
        return json.dumps(self.dhan.fetch_conditional_triggers(), ensure_ascii=True)

    def exit_position(
        self,
        security_id: int,
        side_to_exit: str,
        quantity: int,
        exchange_segment: str = "BSE_EQ",
        product_type: str = "INTRADAY",
        order_type: str = "MARKET",
        price: float = 0.0,
        correlation_id: Optional[str] = None,
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_position_exit_disabled")
        validation_error = self._validate_order_inputs(side_to_exit, quantity)
        if validation_error:
            return validation_error
        tag = self._normalize_correlation_id(correlation_id, prefix="exit")
        response = self.dhan.place_order(
            security_id=security_id,
            exchange_segment=self._normalize_exchange_segment(exchange_segment, int(security_id)),
            transaction_type=str(side_to_exit).strip().upper(),
            quantity=int(quantity),
            order_type=self._normalize_order_type(order_type),
            product_type=str(product_type).strip().upper(),
            price=price,
            trigger_price=0.0,
            disclosed_quantity=0,
            validity="DAY",
            correlation_id=tag,
        )
        payload = {"correlation_id": tag}
        payload.update(response)
        return json.dumps(payload, ensure_ascii=True)

    def exit_all_intraday_positions(self) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_position_exit_disabled")
        positions_response = self.dhan.fetch_positions()
        positions = self._extract_data_list(positions_response)
        exits: List[Dict[str, Any]] = []
        for position in positions:
            try:
                net_qty = int(float(position.get("netQty", 0)))
                if net_qty == 0 or str(position.get("productType", "")).upper() != "INTRADAY":
                    continue
                exit_side = "SELL" if net_qty > 0 else "BUY"
                raw_response = self.place_intraday_equity_order(
                    security_id=int(position.get("securityId")),
                    side=exit_side,
                    quantity=abs(net_qty),
                    order_type="MARKET",
                    exchange_segment=str(position.get("exchangeSegment") or self.default_exchange_segment),
                    correlation_id=f"exit-{uuid.uuid4().hex[:10]}",
                )
                exits.append({"security_id": position.get("securityId"), "response": json.loads(raw_response)})
            except Exception as exc:
                exits.append({"security_id": position.get("securityId"), "status": "failure", "remarks": str(exc)})
        failures = [
            item for item in exits
            if item.get("status") == "failure" or item.get("response", {}).get("status") in {"failure", "blocked"}
        ]
        status = "success" if not failures else ("failure" if len(failures) == len(exits) else "partial_failure")
        return json.dumps({"status": status, "exits": exits}, ensure_ascii=True)

    def activate_kill_switch(self) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_kill_switch_activation_disabled")
        return json.dumps(self.dhan.activate_kill_switch(), ensure_ascii=True)

    def deactivate_kill_switch(self) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_kill_switch_deactivation_disabled")
        return json.dumps(self.dhan.deactivate_kill_switch(), ensure_ascii=True)

    def get_kill_switch_status(self) -> str:
        return json.dumps(self.dhan.fetch_kill_switch_status(), ensure_ascii=True)

    def configure_pnl_exit(
        self,
        profit_value: float,
        loss_value: float,
        product_types_json: str = '["INTRADAY"]',
        enable_kill_switch: bool = False,
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_pnl_exit_configuration_disabled")
        try:
            product_types = json.loads(product_types_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"status": "failure", "remarks": f"invalid_json: {exc}"}, ensure_ascii=True)
        if not isinstance(product_types, list) or not all(isinstance(item, str) for item in product_types):
            return json.dumps({"status": "failure", "remarks": "product_types_json_must_be_array_of_strings"}, ensure_ascii=True)
        return json.dumps(
            self.dhan.configure_pnl_exit(
                profit_value=float(profit_value),
                loss_value=float(loss_value),
                product_types=product_types,
                enable_kill_switch=bool(enable_kill_switch),
            ),
            ensure_ascii=True,
        )

    def disable_pnl_exit(self) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_pnl_exit_disable_disabled")
        return json.dumps(self.dhan.disable_pnl_exit(), ensure_ascii=True)

    def get_pnl_exit(self) -> str:
        return json.dumps(self.dhan.fetch_pnl_exit(), ensure_ascii=True)

    def generate_edis_tpin(self) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_edis_tpin_generation_disabled")
        return json.dumps(self.dhan.generate_edis_tpin(), ensure_ascii=True)

    def get_edis_form(self, isin: str, qty: int, exchange: str = "BSE", segment: str = "EQ", bulk: bool = False) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_edis_form_generation_disabled")
        return json.dumps(
            self.dhan.generate_edis_form(isin=isin, qty=int(qty), exchange=exchange, segment=segment, bulk=bulk),
            ensure_ascii=True,
        )

    def check_edis_status(self, isin: str = "ALL") -> str:
        return json.dumps(self.dhan.fetch_edis_status(isin), ensure_ascii=True)

    def get_ledger_report(self, from_date: str, to_date: str) -> str:
        return json.dumps(self.dhan.fetch_ledger_report(from_date, to_date), ensure_ascii=True)

    def get_trade_history(self, from_date: str, to_date: str, page: int = 0) -> str:
        return json.dumps(self.dhan.fetch_trade_history(from_date, to_date, int(page)), ensure_ascii=True)

    def get_static_ips(self) -> str:
        return json.dumps(self.dhan.fetch_static_ips(), ensure_ascii=True)

    def set_static_ip(self, ip: str, ip_flag: str = "PRIMARY") -> str:
        if not self.allow_live_orders:
            return self._blocked("live_static_ip_set_disabled")
        return json.dumps(
            self.dhan.set_static_ip(ip=ip, ip_flag=str(ip_flag).strip().upper()),
            ensure_ascii=True,
        )

    def modify_static_ip(self, ip: str, ip_flag: str = "PRIMARY") -> str:
        if not self.allow_live_orders:
            return self._blocked("live_static_ip_modify_disabled")
        return json.dumps(
            self.dhan.modify_static_ip(ip=ip, ip_flag=str(ip_flag).strip().upper()),
            ensure_ascii=True,
        )

    def modify_order(
        self,
        order_id: str,
        quantity: int,
        price: float,
        order_type: str = "LIMIT",
        trigger_price: float = 0.0,
        disclosed_quantity: int = 0,
        validity: str = "DAY",
        leg_name: str = "",
    ) -> str:
        if not self.allow_live_orders:
            return json.dumps({"status": "blocked", "remarks": "live_order_modification_disabled"}, ensure_ascii=True)
        response = self.dhan.modify_order(
            order_id=order_id,
            order_type=self._normalize_order_type(order_type),
            quantity=int(quantity),
            price=float(price),
            trigger_price=float(trigger_price),
            disclosed_quantity=int(disclosed_quantity),
            validity=validity,
            leg_name=leg_name,
        )
        return json.dumps(response, ensure_ascii=True)

    def cancel_order(self, order_id: str) -> str:
        if not self.allow_live_orders:
            return json.dumps({"status": "blocked", "remarks": "live_order_cancellation_disabled"}, ensure_ascii=True)
        return json.dumps(self.dhan.cancel_order(order_id), ensure_ascii=True)

    def _env_float(self, key: str, default: float) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except Exception:
            return default

    def _blocked(self, remarks: str) -> str:
        return json.dumps({"status": "blocked", "remarks": remarks}, ensure_ascii=True)

    @staticmethod
    def _normalize_correlation_id(correlation_id: Optional[str], *, prefix: str) -> str:
        """Return a Dhan-compatible correlation ID.

        Dhan accepts only letters, digits, spaces, underscores and hyphens, with
        a maximum length of 30 characters. Preserve a stable hash suffix when a
        model supplies a longer value so distinct requests do not collapse to
        the same truncated ID.
        """
        raw = str(correlation_id or f"{prefix}-{uuid.uuid4().hex[:12]}").strip()
        normalized = re.sub(r"[^A-Za-z0-9 _-]+", "-", raw).strip(" -_")
        if not normalized:
            normalized = f"{prefix}-{uuid.uuid4().hex[:12]}"
        if len(normalized) <= 30:
            return normalized
        digest = sha256(normalized.encode("utf-8")).hexdigest()[:8]
        return f"{normalized[:21]}-{digest}"

    def _validate_order_inputs(self, side: str, quantity: int) -> Optional[str]:
        normalized_side = str(side).strip().upper()
        if normalized_side not in {"BUY", "SELL"}:
            return json.dumps({"status": "failure", "remarks": "invalid_side"}, ensure_ascii=True)
        if int(quantity) <= 0:
            return json.dumps({"status": "failure", "remarks": "invalid_quantity"}, ensure_ascii=True)
        return None

    def _normalize_order_type(self, order_type: Optional[str], allowed: Optional[set[str]] = None) -> str:
        raw = str(order_type or "MARKET").strip().upper().replace(" ", "_")
        aliases = {
            "MKT": "MARKET",
            "LMT": "LIMIT",
            "SL": "STOP_LOSS",
            "SL-L": "STOP_LOSS",
            "SLL": "STOP_LOSS",
            "STOPLOSS": "STOP_LOSS",
            "STOP_LOSS_LIMIT": "STOP_LOSS",
            "SLM": "STOP_LOSS_MARKET",
            "SL-M": "STOP_LOSS_MARKET",
            "STOPLOSSMARKET": "STOP_LOSS_MARKET",
            "STOP_LOSS_MARKET_ORDER": "STOP_LOSS_MARKET",
        }
        normalized = aliases.get(raw, raw)
        allowed_values = allowed or {"LIMIT", "MARKET", "STOP_LOSS", "STOP_LOSS_MARKET"}
        return normalized if normalized in allowed_values else "MARKET"

    def _validate_selected_security_scope(self, security_id: int) -> Optional[str]:
        if self.allowed_security_id is None:
            return None
        if int(security_id) != int(self.allowed_security_id):
            return json.dumps(
                {
                    "status": "blocked",
                    "remarks": "selected_security_scope_violation",
                    "allowed_security_id": int(self.allowed_security_id),
                    "requested_security_id": int(security_id),
                },
                ensure_ascii=True,
            )
        return None

    def _validate_no_selected_stock_overlap(self, security_id: int) -> Optional[str]:
        overlap = self._find_selected_stock_overlap(int(security_id))
        if not overlap:
            return None
        return json.dumps(
            {
                "status": "blocked",
                "remarks": "selected_stock_already_has_order_or_position",
                "security_id": int(security_id),
                "overlap": overlap,
            },
            ensure_ascii=True,
        )

    def _find_selected_stock_overlap(self, security_id: int) -> List[Dict[str, Any]]:
        overlaps: List[Dict[str, Any]] = []
        active_statuses = {
            "PENDING",
            "TRANSIT",
            "PART_TRADED",
            "AMO_REQ_RECEIVED",
            "AFTER_MARKET_ORDER",
            "TRADED_PENDING",
        }

        try:
            positions = self._extract_data_list(self.dhan.fetch_positions())
            for row in positions:
                if str(row.get("securityId") or row.get("security_id") or "") != str(security_id):
                    continue
                if str(row.get("productType") or "").upper() != "INTRADAY":
                    continue
                net_qty = float(row.get("netQty") or 0)
                if net_qty != 0.0:
                    overlaps.append(
                        {
                            "type": "position",
                            "security_id": security_id,
                            "product_type": row.get("productType"),
                            "net_qty": net_qty,
                            "position_type": row.get("positionType"),
                        }
                    )
        except Exception as exc:
            overlaps.append({"type": "position_check_error", "message": str(exc)})

        try:
            orders = self._extract_data_list(self.dhan.fetch_order_book())
            for row in orders:
                if str(row.get("securityId") or row.get("security_id") or "") != str(security_id):
                    continue
                status = str(row.get("orderStatus") or "").upper()
                if status in active_statuses:
                    overlaps.append(
                        {
                            "type": "order",
                            "security_id": security_id,
                            "order_id": row.get("orderId"),
                            "status": status,
                            "transaction_type": row.get("transactionType"),
                            "quantity": row.get("quantity"),
                            "price": row.get("price"),
                        }
                    )
        except Exception as exc:
            overlaps.append({"type": "order_check_error", "message": str(exc)})

        try:
            super_orders = self._extract_data_list(self.dhan.fetch_super_orders())
            for row in super_orders:
                if str(row.get("securityId") or row.get("security_id") or "") != str(security_id):
                    continue
                status = str(row.get("orderStatus") or "").upper()
                leg_details = row.get("legDetails") if isinstance(row.get("legDetails"), list) else []
                has_active_leg = any(str(leg.get("orderStatus") or "").upper() in active_statuses for leg in leg_details if isinstance(leg, dict))
                if status in active_statuses or has_active_leg:
                    overlaps.append(
                        {
                            "type": "super_order",
                            "security_id": security_id,
                            "order_id": row.get("orderId"),
                            "status": status,
                            "transaction_type": row.get("transactionType"),
                            "quantity": row.get("quantity"),
                        }
                    )
        except Exception as exc:
            overlaps.append({"type": "super_order_check_error", "message": str(exc)})

        return overlaps

    def _normalize_exchange_segment(self, exchange_segment: str, security_id: Optional[int] = None) -> str:
        raw = str(exchange_segment or self.default_exchange_segment).strip().upper()
        default = str(self.default_exchange_segment or "BSE_EQ").strip().upper()

        aliases = {
            "EQ": default,
            "EQUITY": default,
            "CASH": default,
            "BSE": "BSE_EQ",
            "NSE": "NSE_EQ",
            "FNO": "NSE_FNO",
            "NFO": "NSE_FNO",
            "MCX": "MCX_COMM",
        }
        normalized = aliases.get(raw, raw)

        # This pipeline's equity universe is BSE-sourced. If the model passes an NSE
        # alias for a BSE-style security id, keep the order/margin call on BSE_EQ.
        if security_id is not None and 500000 <= int(security_id) < 600000 and normalized == "NSE_EQ":
            return "BSE_EQ"

        allowed = {
            "NSE_EQ",
            "NSE_FNO",
            "NSE_CURRENCY",
            "BSE_EQ",
            "BSE_FNO",
            "BSE_CURRENCY",
            "MCX_COMM",
            "IDX_I",
        }
        return normalized if normalized in allowed else default

    def _parse_condition_payload(self, condition_json: str, orders_json: str) -> tuple[Dict[str, Any], List[Dict[str, Any]], Optional[str]]:
        try:
            condition = json.loads(condition_json)
            orders = json.loads(orders_json)
        except json.JSONDecodeError as exc:
            return {}, [], json.dumps({"status": "failure", "remarks": f"invalid_json: {exc}"}, ensure_ascii=True)
        if not isinstance(condition, dict):
            return {}, [], json.dumps({"status": "failure", "remarks": "condition_json_must_be_object"}, ensure_ascii=True)
        if not isinstance(orders, list) or not all(isinstance(item, dict) for item in orders):
            return {}, [], json.dumps({"status": "failure", "remarks": "orders_json_must_be_array_of_objects"}, ensure_ascii=True)
        return condition, orders, None

    def _extract_data_list(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = response.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            data = data.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []
