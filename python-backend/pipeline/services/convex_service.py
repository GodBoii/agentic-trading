from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, Optional

from dotenv import load_dotenv


class ConvexService:
    """Server-only Convex client for trading state and Agno session mirrors."""

    _client: Any = None
    _lock = Lock()
    _env_loaded = False
    _mirrored_hashes: dict[str, str] = {}
    CHUNK_CHARACTERS = 200_000

    @classmethod
    def configured(cls) -> bool:
        cls._load_env()
        return bool(os.getenv("CONVEX_URL", "").strip() and os.getenv("CONVEX_ADMIN_KEY", "").strip())

    @classmethod
    def required(cls) -> bool:
        return os.getenv("CONVEX_REQUIRED", "0").strip().lower() in {"1", "true", "yes"}

    @classmethod
    def client(cls) -> Any:
        cls._load_env()
        with cls._lock:
            if cls._client is not None:
                return cls._client
            url = os.getenv("CONVEX_URL", "").strip()
            admin_key = os.getenv("CONVEX_ADMIN_KEY", "").strip()
            if not url or not admin_key:
                raise RuntimeError("CONVEX_URL and CONVEX_ADMIN_KEY are required.")
            try:
                from convex import ConvexClient
            except ImportError as exc:
                raise RuntimeError("Install the official Convex Python client with `pip install convex`.") from exc
            client = ConvexClient(url)
            client.set_admin_auth(admin_key)
            cls._client = client
            return client

    @classmethod
    def list_trading_configurations(cls) -> list[Dict[str, Any]]:
        rows = cls.client().query("tradingConfigurations:listAll", {})
        return [dict(row) for row in (rows or [])]

    @classmethod
    def upsert_trading_configuration(
        cls,
        user_id: str,
        *,
        enabled: Optional[bool] = None,
        trade_mode: Optional[str] = None,
        trade_amount: Any = ...,
        amount_updated_at: Optional[str] = None,
        status_code: Optional[str] = None,
        updated_at: str,
    ) -> Dict[str, Any]:
        args: Dict[str, Any] = {"supabaseUserId": str(user_id), "updatedAt": updated_at}
        if enabled is not None:
            args["enabled"] = bool(enabled)
        if trade_mode is not None:
            args["tradeMode"] = str(trade_mode)
        if trade_amount is not ...:
            if trade_amount is None:
                args["clearTradeAmount"] = True
            else:
                args["tradeAmount"] = float(trade_amount)
        if amount_updated_at is not None:
            args["amountUpdatedAt"] = str(amount_updated_at)
        if status_code is not None:
            args["statusCode"] = str(status_code)
        result = cls.client().mutation("tradingConfigurations:upsert", args)
        return dict(result or {})

    @classmethod
    def get_order_placement_state(cls, broker: str = "dhan") -> Optional[Dict[str, Any]]:
        result = cls.client().query("orderPlacementStates:get", {"broker": str(broker)})
        return dict(result) if result else None

    @classmethod
    def set_order_placement_state(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = cls.client().mutation("orderPlacementStates:set", dict(payload))
        return dict(result or {})

    @classmethod
    def mirror_session(cls, session: Any) -> None:
        session_dict = cls._as_dict(session)
        session_id = str(session_dict.get("session_id") or session_dict.get("sessionId") or "").strip()
        if not session_id:
            raise RuntimeError("Cannot mirror an Agno session without a session_id.")

        runs = list(session_dict.get("runs") or [])
        session_payload = dict(session_dict)
        session_payload.pop("runs", None)
        payload_json, payload_hash = cls._serialize(session_payload)
        session_type = cls._session_type(session_dict)
        component_id = cls._component_id(session_dict)
        user_id = cls._optional_string(session_dict.get("user_id"))
        run_ids = [cls._run_id(run, session_id, index) for index, run in enumerate(runs)]
        header_key = f"session:{session_id}"

        if cls._mirrored_hashes.get(header_key) != payload_hash:
            args: Dict[str, Any] = {
                "sessionId": session_id,
                "sessionType": session_type,
                "runCount": len(runs),
                "updatedAt": cls._number(session_dict.get("updated_at")) or cls._now_timestamp(),
                "payloadHash": payload_hash,
                "payloadChunks": cls._chunks(payload_json),
            }
            cls._put_optional(args, "userId", user_id)
            cls._put_optional(args, "componentId", component_id)
            cls._put_optional(args, "lastRunId", run_ids[-1] if run_ids else None)
            cls._put_optional(args, "createdAt", cls._number(session_dict.get("created_at")))
            cls.client().mutation("agentSessions:replaceSession", args)
            cls._mirrored_hashes[header_key] = payload_hash

        for index, run in enumerate(runs):
            cls._mirror_run(session_id, user_id, run_ids[index], index, run)

    @classmethod
    def delete_session(cls, session_id: str, user_id: Optional[str] = None) -> bool:
        args: Dict[str, Any] = {"sessionId": str(session_id)}
        cls._put_optional(args, "userId", cls._optional_string(user_id))
        result = cls.client().mutation("agentSessions:deleteSession", args)
        prefix = f"session:{session_id}"
        cls._mirrored_hashes = {
            key: value for key, value in cls._mirrored_hashes.items() if key != prefix
        }
        return bool(result)

    @classmethod
    def _mirror_run(
        cls,
        session_id: str,
        user_id: Optional[str],
        run_id: str,
        run_index: int,
        run: Any,
    ) -> None:
        run_dict = cls._as_dict(run)
        payload_json, payload_hash = cls._serialize(run_dict)
        cache_key = f"run:{run_id}"
        if cls._mirrored_hashes.get(cache_key) == payload_hash:
            return
        args: Dict[str, Any] = {
            "sessionId": session_id,
            "runId": run_id,
            "runIndex": run_index,
            "updatedAt": cls._number(run_dict.get("updated_at")) or cls._now_timestamp(),
            "payloadHash": payload_hash,
            "payloadChunks": cls._chunks(payload_json),
        }
        cls._put_optional(args, "userId", user_id)
        cls._put_optional(args, "status", cls._optional_string(run_dict.get("status")))
        cls._put_optional(args, "contentPreview", cls._content_preview(run_dict))
        cls._put_optional(args, "createdAt", cls._number(run_dict.get("created_at")))
        cls.client().mutation("agentSessions:replaceRun", args)
        cls._mirrored_hashes[cache_key] = payload_hash

    @classmethod
    def _load_env(cls) -> None:
        if cls._env_loaded:
            return
        backend_dir = Path(__file__).resolve().parents[2]
        root_dir = backend_dir.parent
        load_dotenv(root_dir / ".env", override=False)
        load_dotenv(root_dir / ".env.local", override=False)
        load_dotenv(backend_dir / ".env", override=False)
        cls._env_loaded = True

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            result = to_dict()
            if isinstance(result, dict):
                return result
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            result = model_dump(mode="json")
            if isinstance(result, dict):
                return result
        raise TypeError(f"Unsupported Agno session payload: {type(value).__name__}")

    @staticmethod
    def _json_default(value: Any) -> Any:
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json")
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, set):
            return sorted(value, key=str)
        return str(value)

    @classmethod
    def _serialize(cls, value: Any) -> tuple[str, str]:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=cls._json_default,
        )
        return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _chunks(cls, payload: str) -> list[str]:
        return [payload[index : index + cls.CHUNK_CHARACTERS] for index in range(0, len(payload), cls.CHUNK_CHARACTERS)] or [""]

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        normalized = str(value or "").strip()
        return normalized or None

    @classmethod
    def _run_id(cls, run: Any, session_id: str, index: int) -> str:
        data = cls._as_dict(run)
        existing = data.get("run_id") or data.get("runId")
        if existing:
            return str(existing)
        payload, _ = cls._serialize(data)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
        return f"{session_id}:{index}:{digest}"

    @staticmethod
    def _session_type(data: Dict[str, Any]) -> str:
        value = data.get("session_type")
        if value:
            return str(getattr(value, "value", value))
        if data.get("team_id"):
            return "team"
        if data.get("workflow_id"):
            return "workflow"
        return "agent"

    @staticmethod
    def _component_id(data: Dict[str, Any]) -> Optional[str]:
        for key in ("agent_id", "team_id", "workflow_id"):
            if data.get(key):
                return str(data[key])
        return None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _now_timestamp() -> float:
        import time

        return time.time()

    @staticmethod
    def _put_optional(target: Dict[str, Any], key: str, value: Any) -> None:
        if value is not None:
            target[key] = value

    @staticmethod
    def _content_preview(run: Dict[str, Any]) -> Optional[str]:
        for key in ("content", "response", "reasoning_content"):
            value = run.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:2000]
        return None


class ConvexMirroringPostgresDbMixin:
    """Mixin that mirrors Agno's native PostgreSQL session writes to Convex."""

    def upsert_session(self, session: Any, deserialize: Optional[bool] = True) -> Any:
        result = super().upsert_session(session, deserialize=deserialize)
        ConvexService.mirror_session(session)
        return result

    def upsert_sessions(
        self,
        sessions: list[Any],
        deserialize: Optional[bool] = True,
        preserve_updated_at: bool = False,
    ) -> list[Any]:
        result = super().upsert_sessions(
            sessions,
            deserialize=deserialize,
            preserve_updated_at=preserve_updated_at,
        )
        for session in sessions:
            ConvexService.mirror_session(session)
        return result

    def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        deleted = super().delete_session(session_id, user_id=user_id)
        if deleted:
            ConvexService.delete_session(session_id, user_id)
        return deleted

    def delete_sessions(self, session_ids: list[str], user_id: Optional[str] = None) -> None:
        super().delete_sessions(session_ids, user_id=user_id)
        for session_id in session_ids:
            ConvexService.delete_session(session_id, user_id)
