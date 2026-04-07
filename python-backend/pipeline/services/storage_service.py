import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


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
