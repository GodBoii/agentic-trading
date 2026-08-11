from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


class TradingAmountService:
    """Validation and per-user affordability rules for cash-only equity routing."""

    @staticmethod
    def parse(value: Any) -> Optional[float]:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(amount) or amount <= 0:
            return None
        return round(amount, 2)

    @staticmethod
    def quantity(amount: Any, price: Any) -> int:
        parsed_amount = TradingAmountService.parse(amount)
        try:
            parsed_price = float(price)
        except (TypeError, ValueError):
            return 0
        if parsed_amount is None or not math.isfinite(parsed_price) or parsed_price <= 0:
            return 0
        return max(0, int(parsed_amount // parsed_price))

    @staticmethod
    def age_seconds(updated_at: Any, now: Optional[datetime] = None) -> Optional[float]:
        try:
            updated = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None
        current = now or datetime.now(timezone.utc)
        return max(0.0, (current - updated.astimezone(timezone.utc)).total_seconds())

    @staticmethod
    def status(entry: Dict[str, Any], *, max_age_seconds: float, now: Optional[datetime] = None) -> Dict[str, Any]:
        mode = str(entry.get("trade_mode") or ("manual" if entry.get("trade_amount") not in (None, "") else "auto")).lower()
        if mode == "auto":
            return {
                "eligible": True,
                "code": "automatic_balance",
                "message": "Automatic sizing is active. Available broker balance will be checked for each event.",
                "trade_mode": "auto",
                "trade_amount": None,
            }
        amount = TradingAmountService.parse(entry.get("trade_amount"))
        age = TradingAmountService.age_seconds(entry.get("amount_updated_at_utc"), now)
        if amount is None:
            return {"eligible": False, "code": "amount_missing_or_invalid", "message": "The saved manual amount is invalid. Save a positive amount or leave it blank for automatic balance sizing."}
        if age is None:
            return {"eligible": False, "code": "amount_timestamp_unavailable", "message": "The saved trading amount cannot be verified. Save it again."}
        if age > max_age_seconds:
            return {"eligible": False, "code": "amount_stale", "message": "The saved trading amount is stale. Review and save it again."}
        return {"eligible": True, "code": "manual_amount", "message": "Manual trading amount saved. Live monitoring continues automatically.", "trade_mode": "manual", "trade_amount": amount, "age_seconds": age}

    @staticmethod
    def estimated_slippage(depth: Iterable[Dict[str, Any]], *, direction: str, price: float, quantity: int) -> Optional[float]:
        if price <= 0 or quantity <= 0:
            return None
        price_key = "ask_price" if direction == "LONG" else "bid_price"
        quantity_key = "ask_quantity" if direction == "LONG" else "bid_quantity"
        remaining = float(quantity)
        cost = 0.0
        filled = 0.0
        for level in depth:
            try:
                available = max(0.0, float(level.get(quantity_key) or 0))
                level_price = max(0.0, float(level.get(price_key) or 0))
            except (TypeError, ValueError):
                continue
            take = min(remaining, available)
            if take > 0 and level_price > 0:
                cost += take * level_price
                filled += take
                remaining -= take
            if remaining <= 0:
                break
        if filled < quantity or filled <= 0:
            return None
        return abs((cost / filled) - price) / price * 100

