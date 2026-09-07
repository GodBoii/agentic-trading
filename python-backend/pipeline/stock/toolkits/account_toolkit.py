from __future__ import annotations

from typing import Any, Dict, List

from agno.tools import Toolkit

from pipeline.services.dhan_service import DhanService
from pipeline.services.trade_capacity import account_capital, trade_slot_limit
from pipeline.stock.toolkits.markdown_result import tool_result_markdown


class StockAccountToolkit(Toolkit):
    """Read-only account context scoped to one assigned stock."""

    ACTIVE_ORDER_STATUSES = {
        "PENDING",
        "TRANSIT",
        "PART_TRADED",
        "AMO_REQ_RECEIVED",
        "AFTER_MARKET_ORDER",
        "TRADED_PENDING",
    }

    def __init__(self, dhan: DhanService, security_id: int, margin_budget: float) -> None:
        self.dhan = dhan
        self.security_id = int(security_id)
        self.margin_budget = max(0.0, float(margin_budget))
        super().__init__(
            name="stock_account_tools",
            tools=[self.get_account_overview],
        )

    def get_account_overview(self) -> str:
        """Get funds and overlap checks for the assigned stock.

        Other live positions and orders are returned only as aggregate counts.
        This tool is read-only and cannot modify, cancel, convert, or exit them.
        """
        return tool_result_markdown(self.account_overview_payload())

    def account_overview_payload(self) -> Dict[str, Any]:
        """Fetch account and overlap state for the initial decision snapshot."""
        funds_response = self.dhan.fetch_fund_limits()
        positions_response = self.dhan.fetch_positions()
        orders_response = self.dhan.fetch_order_book()
        super_orders_response = self.dhan.fetch_super_orders()

        responses = {
            "funds": funds_response,
            "positions": positions_response,
            "orders": orders_response,
            "super_orders": super_orders_response,
        }
        errors = [
            f"{name}:{self._response_error(response)}"
            for name, response in responses.items()
            if not self._response_succeeded(response)
        ]

        funds = self._extract_dict(funds_response)
        positions = self._extract_list(positions_response)
        orders = self._extract_list(orders_response)
        super_orders = self._extract_list(super_orders_response)

        selected_positions: List[Dict[str, Any]] = []
        active_securities: set[str] = set()
        other_open_positions = 0
        for row in positions:
            if str(row.get("productType") or "").upper() != "INTRADAY":
                continue
            try:
                net_quantity = float(row.get("netQty") or 0)
            except Exception:
                net_quantity = 0.0
            if net_quantity == 0:
                continue
            security_id = row.get("securityId") or row.get("security_id")
            if security_id not in (None, ""):
                active_securities.add(f"{row.get('exchangeSegment') or row.get('exchange_segment') or ''}:{security_id}")
            if self._matches_selected(row):
                selected_positions.append(
                    {
                        "net_quantity": net_quantity,
                        "position_type": row.get("positionType"),
                        "transaction_type": row.get("transactionType"),
                    }
                )
            else:
                other_open_positions += 1

        selected_orders: List[Dict[str, Any]] = []
        other_active_orders = 0
        for row in self._unique_orders([*orders, *super_orders]):
            if not self._is_active_order(row):
                continue
            security_id = row.get("securityId") or row.get("security_id")
            if security_id not in (None, ""):
                active_securities.add(f"{row.get('exchangeSegment') or row.get('exchange_segment') or ''}:{security_id}")
            if self._matches_selected(row):
                selected_orders.append(
                    {
                        "order_id": row.get("orderId") or row.get("order_id"),
                        "status": row.get("orderStatus"),
                        "transaction_type": row.get("transactionType"),
                        "quantity": row.get("quantity"),
                        "price": row.get("price"),
                    }
                )
            else:
                other_active_orders += 1

        payload = {
            "status": "partial" if errors else "success",
            "assigned_security_id": self.security_id,
            "intraday_margin_budget": self.margin_budget,
            "available_balance": self._first_number(
                funds,
                "availabelBalance",
                "availableBalance",
                "withdrawableBalance",
                "sodLimit",
            ),
            "utilized_amount": self._first_number(funds, "utilizedAmount"),
            "account_margin_capacity": account_capital(funds),
            "active_trade_count": len(active_securities),
            "max_concurrent_trades": trade_slot_limit(account_capital(funds)),
            "assigned_stock_overlap": {
                "has_open_intraday_position": bool(selected_positions),
                "has_active_order": bool(selected_orders),
                "positions": selected_positions,
                "orders": selected_orders,
            },
            "other_live_activity": {
                "open_intraday_position_count": other_open_positions,
                "active_order_count": other_active_orders,
                "read_only": True,
            },
            "errors": errors,
        }
        return self._without_empty(payload)

    def _matches_selected(self, row: Dict[str, Any]) -> bool:
        value = row.get("securityId") or row.get("security_id")
        return str(value or "") == str(self.security_id)

    def _is_active_order(self, row: Dict[str, Any]) -> bool:
        status = str(row.get("orderStatus") or "").upper()
        if status in self.ACTIVE_ORDER_STATUSES:
            return True
        legs = row.get("legDetails")
        return isinstance(legs, list) and any(
            isinstance(leg, dict)
            and str(leg.get("orderStatus") or "").upper() in self.ACTIVE_ORDER_STATUSES
            for leg in legs
        )

    @staticmethod
    def _unique_orders(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        seen = set()
        for index, row in enumerate(rows):
            order_id = row.get("orderId") or row.get("order_id")
            key = (
                "order_id",
                str(order_id),
            ) if order_id not in (None, "") else (
                "row",
                str(row.get("securityId") or row.get("security_id") or ""),
                str(row.get("orderStatus") or ""),
                str(row.get("transactionType") or ""),
                str(row.get("quantity") or ""),
                str(row.get("price") or ""),
                index,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    @staticmethod
    def _extract_list(response: Dict[str, Any]) -> List[Dict[str, Any]]:
        data: Any = response.get("data") if isinstance(response, dict) else None
        if isinstance(data, dict):
            data = data.get("data")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    @staticmethod
    def _extract_dict(response: Dict[str, Any]) -> Dict[str, Any]:
        data: Any = response.get("data") if isinstance(response, dict) else None
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _response_succeeded(response: Any) -> bool:
        return isinstance(response, dict) and str(response.get("status") or "").lower() == "success"

    @staticmethod
    def _response_error(response: Any) -> str:
        if not isinstance(response, dict):
            return "invalid_response"
        remarks = response.get("remarks") or response.get("message") or "request_failed"
        return str(remarks)

    @staticmethod
    def _first_number(data: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                try:
                    return float(value)
                except Exception:
                    continue
        return None

    @classmethod
    def _without_empty(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                cleaned = cls._without_empty(item)
                if cleaned not in (None, "", [], {}):
                    result[key] = cleaned
            return result
        if isinstance(value, list):
            return [cls._without_empty(item) for item in value if item not in (None, "", [], {})]
        return value
