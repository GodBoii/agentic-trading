import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class StorageService:
    @staticmethod
    def _resolve_timezone(timezone_name: str):
        aliases = [timezone_name]
        if timezone_name == "Asia/Calcutta":
            aliases.append("Asia/Kolkata")

        for alias in aliases:
            try:
                return ZoneInfo(alias)
            except ZoneInfoNotFoundError:
                continue

        return timezone(timedelta(hours=5, minutes=30), name="IST")

    @staticmethod
    def save_snapshot(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def append_json_line(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str))
            handle.write("\n")

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

        return dt.astimezone(StorageService._resolve_timezone(timezone_name)).date().isoformat()

    @staticmethod
    def is_snapshot_for_market_date(path: Path, timezone_name: str, market_date: str) -> bool:
        payload = StorageService.load_snapshot(path)
        if not payload:
            return False
        return StorageService.snapshot_market_date(payload, timezone_name) == market_date

    @staticmethod
    def stage_snapshot_failure_ratio(payload: Optional[Dict[str, Any]]) -> Optional[float]:
        if not payload:
            return None
        summary = payload.get("summary")
        if not isinstance(summary, dict):
            return None

        stage = str(payload.get("stage") or "")
        if stage == "universe_scanner":
            try:
                scanned = int(summary.get("unique_isins_scanned") or 0)
                failed = int(summary.get("historical_fetch_failed") or 0)
            except (TypeError, ValueError):
                return None
            return min(1.0, failed / scanned) if scanned > 0 else 1.0
        if stage == "intra_finder":
            try:
                expected = int(summary.get("expected_instruments") or 0)
                subscribed = int(summary.get("subscribed_instruments") or 0)
            except (TypeError, ValueError):
                return None
            return max(0.0, 1.0 - (subscribed / expected)) if expected else 1.0
        if stage in {"stage1_sanitation", "universe_scanner"}:
            total = summary.get("historical_candidates")
            if total is None:
                total = summary.get("unique_isins_scanned")
        elif stage in {"stage2_momentum_ignition", "intra_finder"}:
            total = summary.get("input_stage1_count")
            if total is None:
                total = summary.get("expected_instruments")
        else:
            return None

        try:
            total_count = int(total or 0)
            retrieved = int(summary.get("data_retrieved") or 0)
            failed = int(summary.get("failed_fetch") or 0)
        except (TypeError, ValueError):
            return None

        if total_count <= 0:
            return 0.0
        explicit_failure_ratio = failed / total_count
        missing_coverage_ratio = max(0.0, 1.0 - (retrieved / total_count))
        return max(explicit_failure_ratio, missing_coverage_ratio)

    @staticmethod
    def is_stage_snapshot_usable(
        payload: Optional[Dict[str, Any]],
        max_failure_ratio: float,
    ) -> bool:
        if not payload:
            return False
        summary = payload.get("summary")
        if not isinstance(summary, dict):
            return False

        status = str(summary.get("status") or "").strip().lower()
        if status and status != "completed":
            return False

        failure_ratio = StorageService.stage_snapshot_failure_ratio(payload)
        if failure_ratio is None or failure_ratio > max_failure_ratio:
            return False

        stage = str(payload.get("stage") or "")
        if stage in {"stage1_sanitation", "universe_scanner"}:
            try:
                total = int(
                    summary.get("historical_candidates")
                    or summary.get("unique_isins_scanned")
                    or 0
                )
            except (TypeError, ValueError):
                return False
            # Legacy Stage 1 snapshots had no status field. Accept them only
            # when they contain a real, sufficiently complete historical scan.
            return total > 0 or status == "completed"
        if stage in {"stage2_momentum_ignition", "intra_finder"}:
            try:
                total = int(summary.get("input_stage1_count") or 0)
            except (TypeError, ValueError):
                return False
            return total > 0 and status == "completed"
        return False
