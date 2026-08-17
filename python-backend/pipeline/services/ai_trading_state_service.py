from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.services.storage_service import StorageService
from pipeline.services.trading_amount_service import TradingAmountService
from pipeline.services.convex_service import ConvexService


class AITradingStateService:
    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def load_state(path: Path) -> Dict[str, Any]:
        if ConvexService.configured():
            rows = ConvexService.list_trading_configurations()
            user_states = {
                str(row["supabaseUserId"]): {
                    "enabled": bool(row.get("enabled")),
                    "trade_mode": row.get("tradeMode") or "auto",
                    "trade_amount": row.get("tradeAmount"),
                    "amount_updated_at_utc": row.get("amountUpdatedAt"),
                    "status_code": row.get("statusCode"),
                    "updated_at_utc": row.get("updatedAt"),
                }
                for row in rows
                if row.get("supabaseUserId")
            }
            payload = {
                "generated_at_utc": AITradingStateService._now_iso(),
                "enabled_user_ids": sorted(
                    user_id for user_id, entry in user_states.items() if entry["enabled"]
                ),
                "user_states": user_states,
            }
            # This file is an operational cache only; Convex is canonical.
            AITradingStateService.save_state(path, payload)
            return payload
        if ConvexService.required():
            raise RuntimeError(
                "Convex persistence is required but CONVEX_URL or CONVEX_ADMIN_KEY is missing."
            )
        payload = StorageService.load_snapshot(path)
        if isinstance(payload, dict):
            return payload
        return {
            "generated_at_utc": None,
            "enabled_user_ids": [],
            "user_states": {},
        }

    @staticmethod
    def save_state(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        StorageService.save_snapshot(path, payload)

    @staticmethod
    def set_user_state(
        path: Path,
        user_id: str,
        enabled: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if ConvexService.configured():
            metadata = metadata or {}
            trade_amount: Any = ...
            if "trade_amount" in metadata:
                trade_amount = metadata.get("trade_amount")
            trade_mode = metadata.get("trade_mode")
            if trade_mode is None and trade_amount is not ...:
                trade_mode = "auto" if trade_amount is None else "manual"
            ConvexService.upsert_trading_configuration(
                user_id,
                enabled=bool(enabled),
                trade_mode=trade_mode,
                trade_amount=trade_amount,
                amount_updated_at=metadata.get("amount_updated_at_utc"),
                status_code=metadata.get("status_code"),
                updated_at=AITradingStateService._now_iso(),
            )
            return AITradingStateService.load_state(path)

        payload = AITradingStateService.load_state(path)
        user_states = payload.setdefault("user_states", {})
        entry = user_states.get(user_id, {}) if isinstance(user_states.get(user_id), dict) else {}
        entry.update(metadata or {})
        entry["enabled"] = bool(enabled)
        entry["updated_at_utc"] = AITradingStateService._now_iso()
        user_states[user_id] = entry

        enabled_user_ids = sorted(
            key
            for key, value in user_states.items()
            if isinstance(value, dict) and bool(value.get("enabled"))
        )
        payload["enabled_user_ids"] = enabled_user_ids
        payload["generated_at_utc"] = AITradingStateService._now_iso()

        AITradingStateService.save_state(path, payload)
        return payload

    @staticmethod
    def is_any_user_enabled(path: Path) -> bool:
        payload = AITradingStateService.load_state(path)
        enabled_user_ids = payload.get("enabled_user_ids")
        return isinstance(enabled_user_ids, list) and len(enabled_user_ids) > 0

    @staticmethod
    def configured_users(path: Path, *, max_age_seconds: float) -> list[Dict[str, Any]]:
        payload = AITradingStateService.load_state(path)
        results = []
        for user_id, raw_entry in (payload.get("user_states") or {}).items():
            entry = raw_entry if isinstance(raw_entry, dict) else {}
            status = TradingAmountService.status(entry, max_age_seconds=max_age_seconds)
            if not entry.get("enabled") or not status["eligible"]:
                continue
            results.append({"user_id": str(user_id), **entry, **status})
        return results
