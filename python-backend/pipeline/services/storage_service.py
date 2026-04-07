import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo


class StorageService:
    @staticmethod
    def save_snapshot(path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def load_snapshot(path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def build_payload(stage: str, summary: Dict[str, Any], items_key: str, items: list) -> Dict[str, Any]:
        return {
            "stage": stage,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            items_key: items,
        }

    @staticmethod
    def snapshot_market_date(payload: Optional[Dict[str, Any]], timezone_name: str) -> Optional[str]:
        if not payload:
            return None

        generated_at = payload.get("generated_at_utc")
        if not generated_at:
            return None

        try:
            dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        except ValueError:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(ZoneInfo(timezone_name)).date().isoformat()

    @staticmethod
    def is_snapshot_for_market_date(path: Path, timezone_name: str, market_date: str) -> bool:
        payload = StorageService.load_snapshot(path)
        if not payload:
            return False
        return StorageService.snapshot_market_date(payload, timezone_name) == market_date
