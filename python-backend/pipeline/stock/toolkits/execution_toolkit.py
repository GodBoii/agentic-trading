from __future__ import annotations

import json
from threading import Lock
from typing import Any, Dict, Optional

from agno.tools import Toolkit

from pipeline.services.dhan_execution_toolkit import DhanExecutionToolkit
from pipeline.services.dhan_service import DhanService


class StockExecutionCoordinator:
    """Serializes final margin checks and placements across stock agents in one run."""

    def __init__(self) -> None:
        self.placement_lock = Lock()
        self.successful_orders: list[Dict[str, Any]] = []

    def record_success(self, event: Dict[str, Any]) -> None:
        self.successful_orders.append(dict(event))


class StockExecutionToolkit(Toolkit):
    """New-entry execution tools bound to one stock and one margin budget."""

    ALLOWED_ORDER_TYPES = {"LIMIT", "MARKET", "STOP_LOSS", "STOP_LOSS_MARKET"}

    def __init__(
        self,
        dhan: DhanService,
        security_id: int,
        margin_budget: float,
        exchange_segment: Optional[str] = "BSE_EQ",
        coordinator: Optional[StockExecutionCoordinator] = None,
    ) -> None:
        self.security_id = int(security_id)
        self.margin_budget = max(0.0, float(margin_budget))
        self.exchange_segment = str(exchange_segment or "BSE_EQ").upper()
        if self.exchange_segment not in {"NSE_EQ", "BSE_EQ"}:
            raise ValueError("StockExecutionToolkit requires NSE_EQ or BSE_EQ.")
        self.coordinator = coordinator or StockExecutionCoordinator()
        self._dhan_tools = DhanExecutionToolkit(dhan, entry_only=True)
        self._dhan_tools.set_allowed_security_id(self.security_id)
        self._halted = False
        self._protected_attempts = 0
        self._normal_attempts = 0
        self.last_preview: Optional[Dict[str, Any]] = None
        self.last_execution: Optional[Dict[str, Any]] = None
        super().__init__(
            name="stock_execution_tools",
            tools=[
                self.estimate_intraday_quantity,
                self.place_protected_intraday_order,
                self.place_intraday_order,
            ],
        )

    def estimate_intraday_quantity(
        self,
        side: str,
        reference_price: float,
        stop_loss_price: Optional[float] = None,
        max_risk_rupees: Optional[float] = None,
    ) -> str:
        """Calculate quantity from the assigned run's Dhan intraday margin budget.

        Args:
            side: BUY or SELL.
            reference_price: Expected entry price used for the margin calculation.
            stop_loss_price: Intended stop price when risk-based sizing is useful.
            max_risk_rupees: Optional maximum rupee loss for this trade.
        """
        if self._halted:
            return self._failure("execution_halted_after_input_error")
        response = self._dhan_tools.calculate_intraday_equity_order_quantity(
            security_id=self.security_id,
            side=side,
            reference_price=float(reference_price),
            margin_budget=self.margin_budget,
            stop_loss_price=stop_loss_price,
            max_risk_rupees=max_risk_rupees,
            exchange_segment=self.exchange_segment,
        )
        parsed = self._parse(response)
        self.last_preview = parsed
        self._halt_if_input_error(parsed)
        return response

    def place_protected_intraday_order(
        self,
        side: str,
        quantity: int,
        entry_price: float,
        target_price: float,
        stop_loss_price: float,
        order_type: str = "LIMIT",
        trailing_jump: float = 0.0,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Place one protected intraday entry for the assigned stock.

        Quantity is checked against the bound margin budget immediately before
        placement. This tool cannot modify or exit any existing trade.

        Args:
            side: BUY or SELL.
            quantity: Quantity returned by estimate_intraday_quantity.
            entry_price: Intended entry price.
            target_price: Profit target above a BUY entry or below a SELL entry.
            stop_loss_price: Stop below a BUY entry or above a SELL entry.
            order_type: LIMIT or MARKET.
        """
        if self._has_successful_placement():
            return self._failure("entry_order_already_placed")
        if self._halted:
            return self._failure("execution_halted_after_input_error")
        if self._protected_attempts >= 1:
            return self._record_preflight_failure(
                "protected",
                self._failure("protected_order_attempt_limit_reached"),
            )
        normalized_type = self._strict_order_type(order_type, {"LIMIT", "MARKET"})
        if not normalized_type:
            self._halted = True
            return self._record_preflight_failure(
                "protected",
                self._failure("invalid_order_type"),
                side=side,
                quantity=quantity,
                reference_price=entry_price,
            )
        with self.coordinator.placement_lock:
            margin_error = self._validate_final_margin(side, quantity, entry_price)
            if margin_error:
                return self._record_preflight_failure(
                    "protected",
                    margin_error,
                    side=side,
                    quantity=quantity,
                    order_type=normalized_type,
                    reference_price=entry_price,
                )

            self._protected_attempts += 1
            response = self._dhan_tools.place_protected_intraday_super_order(
                security_id=self.security_id,
                side=side,
                quantity=int(quantity),
                entry_price=float(entry_price),
                target_price=float(target_price),
                stop_loss_price=float(stop_loss_price),
                order_type=normalized_type,
                trailing_jump=float(trailing_jump),
                exchange_segment=self.exchange_segment,
                correlation_id=correlation_id,
            )
            return self._record_execution(
                "protected",
                response,
                {
                    "side": str(side).upper(),
                    "quantity": int(quantity),
                    "order_type": normalized_type,
                    "reference_price": float(entry_price),
                },
            )

    def place_intraday_order(
        self,
        side: str,
        quantity: int,
        reference_price: float,
        order_type: str = "MARKET",
        price: float = 0.0,
        trigger_price: float = 0.0,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Place one normal intraday entry for the assigned stock.

        This is an entry-only fallback. It cannot modify, cancel, convert, or
        exit any position or order.

        Args:
            side: BUY or SELL.
            quantity: Quantity returned by estimate_intraday_quantity.
            reference_price: Current price used for the final margin check.
            order_type: LIMIT, MARKET, STOP_LOSS, or STOP_LOSS_MARKET.
            price: Order price; use zero for MARKET.
            trigger_price: Trigger for stop-loss order types; otherwise zero.
        """
        if self._has_successful_placement():
            return self._failure("entry_order_already_placed")
        if self._halted:
            return self._failure("execution_halted_after_input_error")
        if self._normal_attempts >= 1:
            return self._record_preflight_failure(
                "normal",
                self._failure("normal_order_attempt_limit_reached"),
            )
        normalized_type = self._strict_order_type(order_type, self.ALLOWED_ORDER_TYPES)
        if not normalized_type:
            self._halted = True
            return self._record_preflight_failure(
                "normal",
                self._failure("invalid_order_type"),
                side=side,
                quantity=quantity,
                reference_price=reference_price,
            )
        with self.coordinator.placement_lock:
            margin_error = self._validate_final_margin(side, quantity, reference_price, trigger_price)
            if margin_error:
                return self._record_preflight_failure(
                    "normal",
                    margin_error,
                    side=side,
                    quantity=quantity,
                    order_type=normalized_type,
                    reference_price=reference_price,
                )

            self._normal_attempts += 1
            response = self._dhan_tools.place_intraday_equity_order(
                security_id=self.security_id,
                side=side,
                quantity=int(quantity),
                order_type=normalized_type,
                price=float(price),
                trigger_price=float(trigger_price),
                exchange_segment=self.exchange_segment,
                correlation_id=correlation_id,
            )
            return self._record_execution(
                "normal",
                response,
                {
                    "side": str(side).upper(),
                    "quantity": int(quantity),
                    "order_type": normalized_type,
                    "reference_price": float(reference_price),
                },
            )

    def decision_snapshot(self, display_name: str) -> Dict[str, Any]:
        """Build authoritative internal state without parsing the agent's prose."""
        if isinstance(self.last_execution, dict):
            existing_response = self.last_execution.get("response")
            if (
                isinstance(existing_response, dict)
                and str(existing_response.get("status") or "").lower() == "success"
            ):
                self.last_execution["response"] = self._reconcile_order_status(
                    str(self.last_execution.get("kind") or "normal"),
                    existing_response,
                )
        event = self.last_execution or {}
        response = event.get("response") if isinstance(event.get("response"), dict) else {}
        response_status = str(response.get("status") or "").lower()
        broker_status = str(
            response.get("broker_order_status")
            or self._find_value(response, "orderStatus", "order_status")
            or ""
        ).upper()
        requested_quantity = int(event.get("quantity") or 0)
        filled_quantity = self._filled_quantity(response, broker_status, requested_quantity)
        if broker_status == "TRADED":
            execution_status = "traded"
            action = "trade"
        elif broker_status == "PART_TRADED":
            execution_status = "part_traded"
            action = "trade"
        elif broker_status in {
            "PENDING",
            "TRANSIT",
            "AMO_REQ_RECEIVED",
            "AFTER_MARKET_ORDER",
            "TRADED_PENDING",
        }:
            execution_status = "pending"
            action = "pending"
        elif broker_status in {"REJECTED", "CANCELLED", "EXPIRED"}:
            execution_status = broker_status.lower()
            action = "avoid"
        elif response_status == "success":
            execution_status = "submitted"
            action = "pending"
        elif self.last_execution:
            execution_status = "blocked" if response_status == "blocked" else "failed"
            action = "avoid"
        elif self._halted:
            execution_status = "failed"
            action = "avoid"
        else:
            execution_status = "skipped"
            action = "avoid"

        return {
            "selected_security_id": self.security_id,
            "selected_display_name": display_name,
            "action": action,
            "execution_status": execution_status,
            "broker_order_status": broker_status or "UNKNOWN",
            "trade_side": str(event.get("side") or "avoid").lower(),
            "order_type": str(event.get("order_type") or "NONE").upper(),
            "quantity": filled_quantity,
            "filled_quantity": filled_quantity,
            "requested_quantity": requested_quantity,
            "reference_price": float(event.get("reference_price") or 0.0),
            "correlation_id": str(response.get("correlation_id") or "NONE"),
            "order_id": str(self._find_value(response, "orderId", "order_id") or "NONE"),
        }

    def _validate_final_margin(
        self,
        side: str,
        quantity: int,
        reference_price: float,
        trigger_price: float = 0.0,
    ) -> Optional[str]:
        response = self._dhan_tools.calculate_margin_requirement(
            security_id=self.security_id,
            side=side,
            quantity=int(quantity),
            reference_price=float(reference_price),
            exchange_segment=self.exchange_segment,
            trigger_price=float(trigger_price),
        )
        parsed = self._parse(response)
        self._halt_if_input_error(parsed)
        if self._halted:
            return response
        total_margin = self._find_value(
            parsed,
            "totalMargin",
            "total_margin",
            "marginRequired",
            "margin_required",
        )
        try:
            required = float(total_margin)
        except Exception:
            required = 0.0
        if required <= 0:
            return self._failure("invalid_margin_response")
        if required > self.margin_budget:
            return json.dumps(
                {
                    "status": "blocked",
                    "remarks": "quantity_exceeds_intraday_margin_budget",
                    "margin_budget": self.margin_budget,
                    "margin_required": required,
                },
                ensure_ascii=True,
            )
        return None

    def _record_execution(self, kind: str, response: str, request: Dict[str, Any]) -> str:
        parsed = self._parse(response)
        parsed = self._reconcile_order_status(kind, parsed)
        self.last_execution = {
            "kind": kind,
            **request,
            "response": parsed,
        }
        self._halt_if_input_error(parsed)
        if str(parsed.get("status") or "").lower() == "success":
            self.coordinator.record_success(
                {
                    "security_id": self.security_id,
                    "kind": kind,
                    **request,
                    "response": parsed,
                }
            )
        return json.dumps(parsed, ensure_ascii=True)

    def _reconcile_order_status(self, kind: str, response: Dict[str, Any]) -> Dict[str, Any]:
        """Attach the freshest observable broker state without claiming a fill."""
        reconciled = dict(response)
        order_id = self._find_value(response, "orderId", "order_id")
        broker_payload: Optional[Dict[str, Any]] = None
        try:
            if kind == "protected":
                super_orders = self._dhan_tools.dhan.fetch_super_orders()
                candidates = self._extract_rows(super_orders)
                broker_payload = next(
                    (
                        row
                        for row in candidates
                        if str(self._find_value(row, "orderId", "order_id") or "")
                        == str(order_id or "")
                    ),
                    None,
                )
            elif order_id not in (None, ""):
                fetched = self._dhan_tools.dhan.fetch_order_by_id(str(order_id))
                broker_payload = self._extract_first_dict(fetched)
        except Exception as exc:
            reconciled["order_reconciliation_error"] = f"{type(exc).__name__}: {exc}"

        observed = broker_payload or response
        broker_status = self._find_value(observed, "orderStatus", "order_status")
        if broker_status not in (None, ""):
            reconciled["broker_order_status"] = str(broker_status).upper()
        if broker_payload:
            reconciled["broker_order_snapshot"] = broker_payload
        return reconciled

    def _has_successful_placement(self) -> bool:
        if not isinstance(self.last_execution, dict):
            return False
        response = self.last_execution.get("response")
        return isinstance(response, dict) and str(response.get("status") or "").lower() == "success"

    @classmethod
    def _filled_quantity(
        cls,
        response: Dict[str, Any],
        broker_status: str,
        requested_quantity: int,
    ) -> int:
        value = cls._find_value(
            response,
            "filledQty",
            "filledQuantity",
            "filled_quantity",
            "tradedQty",
            "tradedQuantity",
            "quantityTraded",
        )
        try:
            filled = max(0, int(float(value)))
        except Exception:
            filled = 0
        if broker_status == "TRADED" and filled == 0:
            return max(0, requested_quantity)
        return filled

    @classmethod
    def _extract_rows(cls, response: Any) -> list[Dict[str, Any]]:
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        if not isinstance(response, dict):
            return []
        for key in ("data", "orders", "orderList"):
            value = response.get(key)
            rows = cls._extract_rows(value)
            if rows:
                return rows
        return []

    @classmethod
    def _extract_first_dict(cls, response: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(response, dict):
            return None
        data = response.get("data")
        if isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, dict):
                return nested
            return data
        return response

    def _record_preflight_failure(
        self,
        kind: str,
        response: str,
        side: Any = None,
        quantity: Any = None,
        order_type: Any = None,
        reference_price: Any = None,
    ) -> str:
        parsed = self._parse(response)
        self.last_execution = {
            "kind": kind,
            "side": str(side or "").upper(),
            "quantity": int(quantity or 0),
            "order_type": str(order_type or "NONE").upper(),
            "reference_price": float(reference_price or 0.0),
            "response": parsed,
        }
        self._halt_if_input_error(parsed)
        return response

    def _halt_if_input_error(self, payload: Any) -> None:
        serialized = json.dumps(payload, ensure_ascii=True).lower()
        markers = (
            "dh-905",
            "input_exception",
            "invalid parameters",
            "missing required fields",
            "bad values",
            "invalid_side",
            "invalid_quantity",
            "invalid_budget",
            "invalid_margin",
            "invalid_order_type",
        )
        if any(marker in serialized for marker in markers):
            self._halted = True

    @staticmethod
    def _strict_order_type(value: str, allowed: set[str]) -> Optional[str]:
        normalized = str(value or "").strip().upper().replace(" ", "_")
        return normalized if normalized in allowed else None

    @staticmethod
    def _parse(response: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(response)
            return parsed if isinstance(parsed, dict) else {"data": parsed}
        except Exception:
            return {"status": "failure", "remarks": str(response)}

    @classmethod
    def _find_value(cls, value: Any, *keys: str) -> Any:
        if isinstance(value, dict):
            for key in keys:
                if value.get(key) not in (None, ""):
                    return value.get(key)
            for nested in value.values():
                found = cls._find_value(nested, *keys)
                if found not in (None, ""):
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = cls._find_value(nested, *keys)
                if found not in (None, ""):
                    return found
        return None

    @staticmethod
    def _failure(remarks: str) -> str:
        return json.dumps({"status": "failure", "remarks": remarks}, ensure_ascii=True)
