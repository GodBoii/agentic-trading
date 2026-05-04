from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit

from pipeline.services.dhan_service import DhanService


class DhanExecutionToolkit(Toolkit):
    def __init__(self, dhan_service: DhanService):
        super().__init__(
            name="dhan_execution_tools",
            tools=[
                self.get_account_snapshot,
                self.get_order_book,
                self.get_order_by_id,
                self.get_order_by_correlation_id,
                self.get_trade_book,
                self.calculate_margin_requirement,
                self.calculate_equity_order_quantity,
                self.place_intraday_equity_order,
                self.place_protected_intraday_super_order,
                self.get_super_order_list,
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
                self.generate_edis_tpin,
                self.get_edis_form,
                self.check_edis_status,
                self.get_ledger_report,
                self.get_trade_history,
                self.modify_order,
                self.cancel_order,
            ],
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
        return json.dumps(
            self.dhan.calculate_margin_requirement(
                security_id=int(security_id),
                exchange_segment=exchange_segment,
                transaction_type=str(side).strip().upper(),
                quantity=int(quantity),
                product_type=str(product_type).strip().upper(),
                price=float(reference_price),
                trigger_price=float(trigger_price),
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
    ) -> str:
        if not self.allow_live_orders:
            return json.dumps(
                {
                    "status": "blocked",
                    "remarks": "live_order_placement_disabled",
                },
                ensure_ascii=True,
            )

        normalized_side = str(side).strip().upper()
        normalized_order_type = str(order_type).strip().upper()
        if normalized_side not in {"BUY", "SELL"}:
            return json.dumps({"status": "failure", "remarks": "invalid_side"}, ensure_ascii=True)
        if int(quantity) <= 0:
            return json.dumps({"status": "failure", "remarks": "invalid_quantity"}, ensure_ascii=True)

        tag = correlation_id or f"exec-{uuid.uuid4().hex[:12]}"
        order_kwargs = dict(
            security_id=int(security_id),
            exchange_segment=exchange_segment,
            transaction_type=normalized_side,
            quantity=int(quantity),
            order_type=normalized_order_type,
            product_type="INTRADAY",
            price=float(price),
            trigger_price=float(trigger_price),
            disclosed_quantity=int(disclosed_quantity),
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
        correlation_id: Optional[str] = None,
    ) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_super_order_placement_disabled")
        validation_error = self._validate_order_inputs(side, quantity)
        if validation_error:
            return validation_error

        normalized_side = str(side).strip().upper()
        entry = float(entry_price)
        target = float(target_price)
        stop = float(stop_loss_price)
        if normalized_side == "BUY" and not (stop < entry < target):
            return json.dumps({"status": "failure", "remarks": "buy_super_order_requires_stop_below_entry_and_target_above_entry"}, ensure_ascii=True)
        if normalized_side == "SELL" and not (target < entry < stop):
            return json.dumps({"status": "failure", "remarks": "sell_super_order_requires_target_below_entry_and_stop_above_entry"}, ensure_ascii=True)

        tag = correlation_id or f"exec-so-{uuid.uuid4().hex[:10]}"
        response = self.dhan.place_super_order(
            security_id=int(security_id),
            exchange_segment=exchange_segment,
            transaction_type=normalized_side,
            quantity=int(quantity),
            order_type=str(order_type).strip().upper(),
            product_type="INTRADAY",
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
                order_type=order_type,
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
                exchange_segment=exchange_segment,
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
        tag = correlation_id or f"exec-fo-{uuid.uuid4().hex[:10]}"
        response = self.dhan.place_forever_order(
            security_id=int(security_id),
            exchange_segment=exchange_segment,
            transaction_type=str(side).strip().upper(),
            quantity=int(quantity),
            order_flag=str(order_flag).strip().upper(),
            order_type=str(order_type).strip().upper(),
            product_type=str(product_type).strip().upper(),
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
                order_type=str(order_type).strip().upper(),
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
        tag = correlation_id or f"exit-{uuid.uuid4().hex[:10]}"
        response = self.dhan.place_order(
            security_id=security_id,
            exchange_segment=exchange_segment,
            transaction_type=str(side_to_exit).strip().upper(),
            quantity=int(quantity),
            order_type=str(order_type).strip().upper(),
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
        return json.dumps({"status": "success", "exits": exits}, ensure_ascii=True)

    def activate_kill_switch(self) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_kill_switch_activation_disabled")
        return json.dumps(self.dhan.activate_kill_switch(), ensure_ascii=True)

    def deactivate_kill_switch(self) -> str:
        if not self.allow_live_orders:
            return self._blocked("live_kill_switch_deactivation_disabled")
        return json.dumps(self.dhan.deactivate_kill_switch(), ensure_ascii=True)

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
            order_type=order_type,
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

    def _validate_order_inputs(self, side: str, quantity: int) -> Optional[str]:
        normalized_side = str(side).strip().upper()
        if normalized_side not in {"BUY", "SELL"}:
            return json.dumps({"status": "failure", "remarks": "invalid_side"}, ensure_ascii=True)
        if int(quantity) <= 0:
            return json.dumps({"status": "failure", "remarks": "invalid_quantity"}, ensure_ascii=True)
        return None

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
