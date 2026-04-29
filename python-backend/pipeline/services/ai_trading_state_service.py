from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.services.storage_service import StorageService


class AITradingStateService:
    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def load_state(path: Path) -> Dict[str, Any]:
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
