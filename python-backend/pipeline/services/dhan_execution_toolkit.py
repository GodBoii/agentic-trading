from __future__ import annotations

import json
import os
import uuid
from typing import Optional

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
                self.calculate_equity_order_quantity,
                self.place_intraday_equity_order,
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
        response = self.dhan.place_order(
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
            should_slice=should_slice,
        )
        payload = {"correlation_id": tag}
        payload.update(response)
        return json.dumps(payload, ensure_ascii=True)

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
