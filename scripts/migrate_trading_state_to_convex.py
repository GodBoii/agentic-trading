"""One-time migration of the legacy local trading configuration into Convex."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "python-backend"
sys.path.insert(0, str(BACKEND))

from pipeline.services.convex_service import ConvexService  # noqa: E402


def main() -> int:
    state_path = BACKEND / "ai_trading_state.json"
    if not state_path.is_file():
        print(f"No legacy state file found at {state_path}")
        return 0
    if not ConvexService.configured():
        raise RuntimeError("Set CONVEX_URL and CONVEX_ADMIN_KEY before running the migration.")

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    migrated = 0
    for user_id, raw_entry in (payload.get("user_states") or {}).items():
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        updated_at = str(
            entry.get("updated_at_utc")
            or entry.get("amount_updated_at_utc")
            or payload.get("generated_at_utc")
            or ""
        ).strip()
        if not updated_at:
            continue
        ConvexService.upsert_trading_configuration(
            str(user_id),
            enabled=bool(entry.get("enabled")),
            trade_mode=str(entry.get("trade_mode") or "auto"),
            trade_amount=entry.get("trade_amount"),
            amount_updated_at=entry.get("amount_updated_at_utc"),
            status_code=entry.get("status_code"),
            updated_at=updated_at,
        )
        migrated += 1

    print(f"Migrated {migrated} trading configuration(s) to Convex.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
