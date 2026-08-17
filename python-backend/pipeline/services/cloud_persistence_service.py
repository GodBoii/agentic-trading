from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv


class CloudPersistenceService:
    """Canonical cloud persistence for Agno runs and their image inputs."""

    _db: Any = None
    _db_lock = Lock()
    _table_lock = Lock()
    _session_table_ready = False
    _env_loaded = False

    @classmethod
    def agno_db(cls) -> Any:
        cls._load_env()
        with cls._db_lock:
            if cls._db is not None:
                return cls._db

            db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
            if not db_url:
                raise RuntimeError(
                    "SUPABASE_DB_URL is required for native Agno run persistence. "
                    "Use the Supabase Session Pooler connection string."
                )

            try:
                from agno.db.postgres import PostgresDb
            except ImportError as exc:
                raise RuntimeError(
                    "Agno PostgreSQL dependencies are unavailable. "
                    "Install sqlalchemy and psycopg[binary]."
                ) from exc

            from pipeline.services.convex_service import (
                ConvexMirroringPostgresDbMixin,
                ConvexService,
            )

            db_class: Any = PostgresDb
            if ConvexService.configured():
                db_class = type(
                    "ConvexMirroringPostgresDb",
                    (ConvexMirroringPostgresDbMixin, PostgresDb),
                    {},
                )
            elif ConvexService.required():
                raise RuntimeError(
                    "Convex persistence is required but CONVEX_URL or "
                    "CONVEX_ADMIN_KEY is missing."
                )

            cls._db = db_class(
                db_url=cls._sqlalchemy_url(db_url),
                db_schema=os.getenv("AGNO_DB_SCHEMA", "public"),
                session_table=os.getenv("AGNO_SESSION_TABLE", "agno_sessions"),
            )
            return cls._db

    @classmethod
    def validate_agno_db(cls) -> Any:
        db = cls.agno_db()
        with cls._table_lock:
            if cls._session_table_ready:
                return db
            try:
                db._get_table(  # Agno's native lazy table initializer.
                    table_type="sessions",
                    create_table_if_not_found=True,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Supabase Postgres is unavailable for native Agno persistence."
                ) from exc
            cls._session_table_ready = True
        return db

    @classmethod
    def upload_image(cls, local_path: str | Path, storage_path: str) -> dict[str, str]:
        cls._load_env()
        source = Path(local_path)
        if not source.is_file():
            raise RuntimeError(f"Chart image does not exist: {source}")

        supabase_url = (
            os.getenv("SUPABASE_URL")
            or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            or ""
        ).rstrip("/")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        bucket = os.getenv("SUPABASE_TRADE_SESSIONS_BUCKET", "trade-sessions")
        if not supabase_url or not service_role_key:
            raise RuntimeError(
                "SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL) and "
                "SUPABASE_SERVICE_ROLE_KEY are required for chart uploads."
            )

        normalized_path = storage_path.replace("\\", "/").lstrip("/")
        encoded_bucket = quote(bucket, safe="")
        encoded_path = quote(normalized_path, safe="/")
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        upload_url = f"{supabase_url}/storage/v1/object/{encoded_bucket}/{encoded_path}"
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": content_type,
            "x-upsert": "true",
        }

        with source.open("rb") as image_file:
            response = requests.post(
                upload_url,
                headers=headers,
                data=image_file,
                timeout=60,
            )
        if not response.ok:
            detail = response.text.strip().replace("\n", " ")[:500]
            raise RuntimeError(
                f"Supabase image upload failed ({response.status_code}): {detail}"
            )

        public_url = (
            f"{supabase_url}/storage/v1/object/public/"
            f"{encoded_bucket}/{encoded_path}"
        )
        return {
            "bucket": bucket,
            "storage_path": normalized_path,
            "cloud_url": public_url,
        }

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
    def _sqlalchemy_url(db_url: str) -> str:
        normalized = db_url.strip()
        if normalized.startswith("postgresql+"):
            return normalized
        if normalized.startswith("postgres://"):
            return f"postgresql+psycopg://{normalized[len('postgres://'):]}"
        if normalized.startswith("postgresql://"):
            return f"postgresql+psycopg://{normalized[len('postgresql://'):]}"
        raise RuntimeError(
            "SUPABASE_DB_URL must start with postgres:// or postgresql://."
        )
