import base64
import hashlib
import json
import mimetypes
import os
import re
import uuid
from urllib.parse import urlparse
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import requests
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, text

import config
from database_config import get_sqlalchemy_database_url
from r2_client import get_r2_client


_TENANT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_DB_NAME_RE = re.compile(r"^[a-z0-9-]{3,64}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_RESERVED_SLUGS = {
    "www",
    "api",
    "app",
    "admin",
    "mail",
    "smtp",
    "imap",
    "pop",
    "ftp",
    "cdn",
    "status",
    "ns1",
    "ns2",
}


def _db_url_sqlalchemy() -> str:
    return get_sqlalchemy_database_url()


_engine = create_engine(
    _db_url_sqlalchemy(),
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
)


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise ValueError(f"Missing required environment variable: {name}")
    return val


def get_runtime_query_endpoint() -> str:
    """
    Public endpoint that deployed websites should call for runtime database queries.
    If DEPLOY_RUNTIME_API_BASE_URL is unset, returns a relative path.
    """
    base = ""
    for key in (
        "DEPLOY_RUNTIME_API_BASE_URL",
        "BACKEND_PUBLIC_URL",
        "PUBLIC_API_BASE_URL",
        "API_BASE_URL",
    ):
        val = (os.getenv(key) or "").strip()
        if val:
            base = val.rstrip("/")
            break
    path = "/api/deploy/runtime/query"
    return f"{base}{path}" if base else path


def _fernet() -> Fernet:
    key = _require_env("DEPLOY_SECRET_KEY")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise ValueError(
            "DEPLOY_SECRET_KEY must be a valid Fernet key. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher: str) -> str:
    try:
        return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret with DEPLOY_SECRET_KEY") from exc


def preflight_check() -> dict[str, Any]:
    required = [
        "DEPLOY_DOMAIN",
        "R2_SITES_BUCKET",
        "TURSO_ORG_SLUG",
        "TURSO_GROUP",
        "TURSO_API_TOKEN",
        "DEPLOY_SECRET_KEY",
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ]
    missing = [k for k in required if not os.getenv(k)]

    checks = {
        "timestamp": _utc_now_iso(),
        "missing_env": missing,
        "database": False,
        "r2": False,
        "turso_token": False,
    }

    if missing:
        return {"ok": False, "checks": checks}

    with _engine.connect() as conn:
        conn.execute(text("select 1"))
    checks["database"] = True

    try:
        r2 = get_r2_client()
        r2.client.head_bucket(Bucket=os.getenv("R2_SITES_BUCKET"))
        checks["r2"] = True
    except Exception:
        checks["r2"] = False

    turso_base = "https://api.turso.tech/v1/auth/validate"
    resp = requests.get(
        turso_base,
        headers={"Authorization": f"Bearer {os.getenv('TURSO_API_TOKEN')}"},
        timeout=15,
    )
    checks["turso_token"] = resp.status_code == 200

    return {"ok": all([checks["database"], checks["r2"], checks["turso_token"]]), "checks": checks}


def ensure_deploy_tables() -> None:
    ddl = [
        """
        create table if not exists platform_sites (
          id uuid primary key,
          user_id uuid not null,
          project_name text not null,
          slug text not null unique,
          status text not null default 'draft',
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );
        """,
        """
        create table if not exists platform_domains (
          id uuid primary key,
          site_id uuid not null references platform_sites(id) on delete cascade,
          hostname text not null unique,
          is_primary boolean not null default true,
          ssl_status text not null default 'active',
          created_at timestamptz not null default now()
        );
        """,
        """
        create table if not exists platform_deployments (
          id uuid primary key,
          site_id uuid not null references platform_sites(id) on delete cascade,
          version int not null,
          r2_prefix text not null,
          status text not null default 'queued',
          build_meta jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          activated_at timestamptz
        );
        """,
        """
        create unique index if not exists uniq_site_version
          on platform_deployments(site_id, version);
        """,
        """
        create table if not exists platform_site_databases (
          id uuid primary key,
          site_id uuid not null unique references platform_sites(id) on delete cascade,
          turso_org_slug text not null,
          turso_group text not null,
          turso_db_name text not null unique,
          turso_db_hostname text not null,
          encrypted_admin_token text not null,
          encrypted_rw_token text not null,
          encrypted_ro_token text,
          created_at timestamptz not null default now(),
          rotated_at timestamptz
        );
        """,
    ]
    with _engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


def _validate_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not _TENANT_RE.fullmatch(s):
        raise ValueError("Invalid slug. Use lowercase letters, numbers, and dashes.")
    if s in _RESERVED_SLUGS:
        raise ValueError(f"Slug '{s}' is reserved")
    return s


def _ensure_site_owned(site_id: str, user_id: str) -> dict[str, Any]:
    with _engine.connect() as conn:
        row = conn.execute(
            text("select id, user_id, slug, status from platform_sites where id = :site_id"),
            {"site_id": site_id},
        ).mappings().first()
    if not row:
        raise ValueError("Site not found")
    if str(row["user_id"]) != str(user_id):
        raise PermissionError("Unauthorized site access")
    return dict(row)


def create_or_get_site(site_id: str, user_id: str, project_name: str, slug: str) -> dict[str, Any]:
    safe_slug = _validate_slug(slug)
    with _engine.begin() as conn:
        existing = conn.execute(
            text("select id, user_id, project_name, slug, status from platform_sites where id = :site_id"),
            {"site_id": site_id},
        ).mappings().first()
        if existing:
            if str(existing["user_id"]) != str(user_id):
                raise PermissionError("Unauthorized site access")

            slug_owner = conn.execute(
                text("select id from platform_sites where slug = :slug and id <> :site_id"),
                {"slug": safe_slug, "site_id": site_id},
            ).mappings().first()
            if slug_owner:
                raise ValueError(f"Slug '{safe_slug}' is already in use")

            conn.execute(
                text(
                    """
                    update platform_sites
                    set project_name = :project_name,
                        slug = :slug,
                        updated_at = now()
                    where id = :site_id
                    """
                ),
                {
                    "site_id": site_id,
                    "project_name": project_name,
                    "slug": safe_slug,
                },
            )
            return {
                "id": site_id,
                "user_id": user_id,
                "project_name": project_name,
                "slug": safe_slug,
                "status": existing["status"],
            }

        slug_owner = conn.execute(
            text("select id from platform_sites where slug = :slug"),
            {"slug": safe_slug},
        ).mappings().first()
        if slug_owner:
            raise ValueError(f"Slug '{safe_slug}' is already in use")

        conn.execute(
            text(
                """
                insert into platform_sites (id, user_id, project_name, slug, status)
                values (:id, :user_id, :project_name, :slug, 'draft')
                """
            ),
            {
                "id": site_id,
                "user_id": user_id,
                "project_name": project_name,
                "slug": safe_slug,
            },
        )
    return {
        "id": site_id,
        "user_id": user_id,
        "project_name": project_name,
        "slug": safe_slug,
        "status": "draft",
    }


def assign_subdomain(site_id: str, user_id: str) -> dict[str, Any]:
    site = _ensure_site_owned(site_id=site_id, user_id=user_id)
    deploy_domain = _require_env("DEPLOY_DOMAIN").lower()
    hostname = f"{site['slug']}.{deploy_domain}"

    with _engine.begin() as conn:
        conflicting = conn.execute(
            text(
                """
                select site_id
                from platform_domains
                where hostname = :hostname and site_id <> :site_id
                """
            ),
            {"hostname": hostname, "site_id": site_id},
        ).mappings().first()
        if conflicting:
            raise ValueError(f"Hostname '{hostname}' is already assigned to another site")

        conn.execute(
            text("delete from platform_domains where site_id = :site_id"),
            {"site_id": site_id},
        )
        conn.execute(
            text(
                """
                insert into platform_domains (id, site_id, hostname, is_primary, ssl_status)
                values (:id, :site_id, :hostname, true, 'active')
                """
            ),
            {"id": str(uuid.uuid4()), "site_id": site_id, "hostname": hostname},
        )
    return {"site_id": site_id, "hostname": hostname}


def _sanitize_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    p = p.lstrip("/")
    if not p or p.endswith("/"):
        raise ValueError("Invalid file path")
    if ".." in p.split("/"):
        raise ValueError("Invalid file path")
    return p


def _next_deployment_version(site_id: str) -> int:
    with _engine.connect() as conn:
        row = conn.execute(
            text("select coalesce(max(version), 0) as v from platform_deployments where site_id = :site_id"),
            {"site_id": site_id},
        ).mappings().first()
    return int(row["v"]) + 1


@dataclass
class UploadResult:
    deployment_id: str
    version: int
    r2_prefix: str
    files_uploaded: int


def upload_site_files(site_id: str, user_id: str, files: list[dict[str, Any]]) -> UploadResult:
    site = _ensure_site_owned(site_id=site_id, user_id=user_id)
    if not files:
        raise ValueError("No files provided")

    version = _next_deployment_version(site_id)
    deployment_id = str(uuid.uuid4())
    prefix = f"sites/{site_id}/deployments/{deployment_id}"
    bucket = _require_env("R2_SITES_BUCKET")

    r2 = get_r2_client()
    uploaded = 0
    for item in files:
        path = _sanitize_path(str(item.get("path", "")))
        content_type = item.get("content_type") or mimetypes.guess_type(path)[0] or "application/octet-stream"

        if "content_base64" in item and item["content_base64"] is not None:
            content_bytes = base64.b64decode(item["content_base64"])
        elif "content" in item and item["content"] is not None:
            content_bytes = str(item["content"]).encode("utf-8")
        else:
            raise ValueError(f"File '{path}' missing content")

        key = f"{prefix}/{path}"
        r2.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content_bytes,
            ContentType=content_type,
            Metadata={"site-id": site_id, "deployment-id": deployment_id, "slug": site["slug"]},
        )
        uploaded += 1

    with _engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into platform_deployments (id, site_id, version, r2_prefix, status, build_meta)
                values (:id, :site_id, :version, :r2_prefix, 'uploading', cast(:build_meta as jsonb))
                """
            ),
            {
                "id": deployment_id,
                "site_id": site_id,
                "version": version,
                "r2_prefix": prefix,
                "build_meta": json.dumps({"uploaded_files": uploaded}),
            },
        )

    return UploadResult(
        deployment_id=deployment_id,
        version=version,
        r2_prefix=prefix,
        files_uploaded=uploaded,
    )


def _delete_r2_prefix(prefix: str) -> int:
    safe_prefix = str(prefix or "").strip().rstrip("/")
    if not safe_prefix:
        return 0

    bucket = _require_env("R2_SITES_BUCKET")
    r2 = get_r2_client()
    paginator = r2.client.get_paginator("list_objects_v2")
    deleted = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=f"{safe_prefix}/"):
        keys = [
            {"Key": str(item.get("Key"))}
            for item in (page.get("Contents", []) or [])
            if item.get("Key")
        ]
        if not keys:
            continue

        for start in range(0, len(keys), 1000):
            batch = keys[start:start + 1000]
            response = r2.client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": batch, "Quiet": True},
            )
            deleted += len(response.get("Deleted", []) or [])

    return deleted


def prune_site_deployments(site_id: str, user_id: str, keep_count: int = 2) -> dict[str, Any]:
    _ensure_site_owned(site_id=site_id, user_id=user_id)
    keep = max(1, int(keep_count or 1))

    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select id, version, r2_prefix, status
                from platform_deployments
                where site_id = :site_id
                order by (status = 'active') desc, version desc, created_at desc
                """
            ),
            {"site_id": site_id},
        ).mappings().all()

    if len(rows) <= keep:
        return {"deleted_deployments": 0, "deleted_objects": 0}

    victims = [dict(row) for row in rows[keep:]]
    deleted_objects = 0

    for victim in victims:
        deleted_objects += _delete_r2_prefix(str(victim.get("r2_prefix") or ""))

    with _engine.begin() as conn:
        for victim in victims:
            conn.execute(
                text("delete from platform_deployments where site_id = :site_id and id = :deployment_id"),
                {"site_id": site_id, "deployment_id": str(victim["id"])},
            )

    return {
        "deleted_deployments": len(victims),
        "deleted_objects": deleted_objects,
    }


def _safe_db_name(site_id: str) -> str:
    raw = f"site-{site_id}".lower().replace("_", "-")
    cleaned = re.sub(r"[^a-z0-9-]", "-", raw)
    compact = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if len(compact) > 52:
        compact = compact[:52].rstrip("-")
    suffix = uuid.uuid4().hex[:8]
    name = f"{compact}-{suffix}"
    if not _DB_NAME_RE.fullmatch(name):
        raise ValueError("Generated Turso database name is invalid")
    return name


def provision_turso_database(site_id: str, user_id: str) -> dict[str, Any]:
    _ensure_site_owned(site_id=site_id, user_id=user_id)
    org_slug = _require_env("TURSO_ORG_SLUG")
    group = _require_env("TURSO_GROUP")
    api_token = _require_env("TURSO_API_TOKEN")

    with _engine.connect() as conn:
        existing = conn.execute(
            text(
                """
                select turso_db_name, turso_db_hostname
                from platform_site_databases
                where site_id = :site_id
                """
            ),
            {"site_id": site_id},
        ).mappings().first()
    if existing:
        return {
            "site_id": site_id,
            "database_name": existing["turso_db_name"],
            "hostname": existing["turso_db_hostname"],
            "already_exists": True,
        }

    db_name = _safe_db_name(site_id)
    base = f"https://api.turso.tech/v1/organizations/{org_slug}/databases"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

    create_resp = requests.post(base, headers=headers, json={"name": db_name, "group": group}, timeout=30)
    if create_resp.status_code not in (200, 201):
        raise RuntimeError(f"Turso create database failed: {create_resp.status_code} {create_resp.text}")

    db_obj = (create_resp.json() or {}).get("database") or {}
    hostname = db_obj.get("Hostname") or f"{db_name}-{org_slug}.turso.io"

    rw_url = f"{base}/{db_name}/auth/tokens?authorization=full-access&expiration=90d"
    ro_url = f"{base}/{db_name}/auth/tokens?authorization=read-only&expiration=90d"
    admin_url = f"{base}/{db_name}/auth/tokens?authorization=full-access&expiration=365d"

    rw_resp = requests.post(rw_url, headers=headers, timeout=30)
    ro_resp = requests.post(ro_url, headers=headers, timeout=30)
    admin_resp = requests.post(admin_url, headers=headers, timeout=30)
    for resp, label in [(rw_resp, "rw"), (ro_resp, "ro"), (admin_resp, "admin")]:
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Turso create {label} token failed: {resp.status_code} {resp.text}")

    rw_token = rw_resp.json().get("jwt")
    ro_token = ro_resp.json().get("jwt")
    admin_token = admin_resp.json().get("jwt")
    if not rw_token or not ro_token or not admin_token:
        raise RuntimeError("Turso token generation returned an empty token")

    with _engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into platform_site_databases (
                  id, site_id, turso_org_slug, turso_group, turso_db_name, turso_db_hostname,
                  encrypted_admin_token, encrypted_rw_token, encrypted_ro_token
                )
                values (
                  :id, :site_id, :org_slug, :group, :db_name, :db_hostname,
                  :admin_token, :rw_token, :ro_token
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "site_id": site_id,
                "org_slug": org_slug,
                "group": group,
                "db_name": db_name,
                "db_hostname": hostname,
                "admin_token": encrypt_secret(admin_token),
                "rw_token": encrypt_secret(rw_token),
                "ro_token": encrypt_secret(ro_token),
            },
        )

    return {"site_id": site_id, "database_name": db_name, "hostname": hostname, "already_exists": False}


def get_site_db_credentials(site_id: str, user_id: str, include_admin: bool = False) -> dict[str, Any]:
    _ensure_site_owned(site_id=site_id, user_id=user_id)
    with _engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select turso_db_name, turso_db_hostname, encrypted_rw_token, encrypted_ro_token, encrypted_admin_token
                from platform_site_databases
                where site_id = :site_id
                """
            ),
            {"site_id": site_id},
        ).mappings().first()
    if not row:
        raise ValueError("No database provisioned for this site")

    out = {
        "database_name": row["turso_db_name"],
        "hostname": row["turso_db_hostname"],
        "url": f"libsql://{row['turso_db_hostname']}",
        "rw_token": decrypt_secret(row["encrypted_rw_token"]),
        "ro_token": decrypt_secret(row["encrypted_ro_token"]) if row.get("encrypted_ro_token") else None,
    }
    if include_admin:
        out["admin_token"] = decrypt_secret(row["encrypted_admin_token"])
    return out


def resolve_public_site_hostname(hostname: str) -> dict[str, Any]:
    """
    Resolve a deployed site by hostname without requiring a platform user token.
    Used for runtime website requests that originate from deployed subdomains.
    """
    host = (hostname or "").strip().lower().rstrip(".")
    if ":" in host:
        host = host.split(":", 1)[0]
    if not host:
        raise ValueError("hostname is required")

    with _engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select
                  s.id,
                  s.slug,
                  s.status,
                  d.hostname
                from platform_domains d
                join platform_sites s on s.id = d.site_id
                where lower(d.hostname) = :hostname
                order by d.is_primary desc, d.created_at asc
                limit 1
                """
            ),
            {"hostname": host},
        ).mappings().first()
        if not row:
            raise ValueError("Site not found for hostname")

        active_dep = conn.execute(
            text(
                """
                select id
                from platform_deployments
                where site_id = :site_id and status = 'active'
                order by activated_at desc nulls last, created_at desc
                limit 1
                """
            ),
            {"site_id": str(row["id"])},
        ).mappings().first()

    if str(row["status"]) != "active":
        raise ValueError("Site is not active")
    if not active_dep:
        raise ValueError("No active deployment for hostname")

    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "status": row["status"],
        "hostname": row["hostname"],
        "active_deployment_id": str(active_dep["id"]),
    }


def get_site_runtime_db_credentials(site_id: str) -> dict[str, Any]:
    """
    Fetch decrypted runtime DB credentials for an active site.
    This is intended for server-side runtime routing only.
    """
    with _engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select
                  s.status,
                  db.turso_db_name,
                  db.turso_db_hostname,
                  db.encrypted_rw_token,
                  db.encrypted_ro_token
                from platform_sites s
                join platform_site_databases db on db.site_id = s.id
                where s.id = :site_id
                """
            ),
            {"site_id": site_id},
        ).mappings().first()
    if not row:
        raise ValueError("No database provisioned for this site")
    if str(row["status"]) != "active":
        raise ValueError("Site is not active")

    return {
        "database_name": row["turso_db_name"],
        "hostname": row["turso_db_hostname"],
        "url": f"libsql://{row['turso_db_hostname']}",
        "rw_token": decrypt_secret(row["encrypted_rw_token"]),
        "ro_token": decrypt_secret(row["encrypted_ro_token"]) if row.get("encrypted_ro_token") else None,
    }


def activate_deployment(site_id: str, user_id: str, deployment_id: str) -> dict[str, Any]:
    _ensure_site_owned(site_id=site_id, user_id=user_id)
    with _engine.begin() as conn:
        dep = conn.execute(
            text(
                """
                select id, site_id, r2_prefix
                from platform_deployments
                where id = :deployment_id and site_id = :site_id
                """
            ),
            {"deployment_id": deployment_id, "site_id": site_id},
        ).mappings().first()
        if not dep:
            raise ValueError("Deployment not found")

        conn.execute(
            text(
                """
                update platform_deployments
                set status = 'inactive'
                where site_id = :site_id and id <> :deployment_id and status = 'active'
                """
            ),
            {"site_id": site_id, "deployment_id": deployment_id},
        )
        conn.execute(
            text(
                """
                update platform_deployments
                set status = 'active', activated_at = now()
                where id = :deployment_id
                """
            ),
            {"deployment_id": deployment_id},
        )
        conn.execute(
            text("update platform_sites set status = 'active', updated_at = now() where id = :site_id"),
            {"site_id": site_id},
        )

        host_row = conn.execute(
            text("select hostname from platform_domains where site_id = :site_id and is_primary = true"),
            {"site_id": site_id},
        ).mappings().first()

    if not host_row:
        host = assign_subdomain(site_id=site_id, user_id=user_id)["hostname"]
    else:
        host = host_row["hostname"]

    retention = prune_site_deployments(site_id=site_id, user_id=user_id, keep_count=2)
    return {
        "site_id": site_id,
        "deployment_id": deployment_id,
        "url": f"https://{host}",
        "active": True,
        **retention,
    }


def upsert_site_manifest(site_id: str, user_id: str, deployment_id: str) -> dict[str, Any]:
    site = _ensure_site_owned(site_id=site_id, user_id=user_id)
    creds: Optional[dict[str, Any]] = None
    try:
        creds = get_site_db_credentials(site_id=site_id, user_id=user_id, include_admin=False)
    except ValueError:
        # Phase-gated deploy: allow static-only deploys without a provisioned DB.
        creds = None
    with _engine.connect() as conn:
        dep = conn.execute(
            text("select r2_prefix from platform_deployments where id = :id and site_id = :site_id"),
            {"id": deployment_id, "site_id": site_id},
        ).mappings().first()
    if not dep:
        raise ValueError("Deployment not found")

    manifest = {
        "site_id": site_id,
        "slug": site["slug"],
        "deployment_id": deployment_id,
        "r2_prefix": dep["r2_prefix"],
        "db": (
            {
                "url": creds["url"],
                "hostname": creds["hostname"],
                "database_name": creds["database_name"],
                "runtime_query_endpoint": get_runtime_query_endpoint(),
            }
            if creds
            else None
        ),
        "updated_at": _utc_now_iso(),
    }

    bucket = _require_env("R2_SITES_BUCKET")
    key = f"manifests/{site['slug']}.json"
    body = json.dumps(manifest, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    etag = hashlib.sha256(body).hexdigest()
    r2 = get_r2_client()
    r2.client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        Metadata={"site-id": site_id, "deployment-id": deployment_id, "sha256": etag},
    )
    return {"manifest_key": key, "sha256": etag}


def _normalize_site_ref(site_ref: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns a tuple: (raw_ref, normalized_slug_candidate, normalized_hostname_candidate).
    """
    if not site_ref:
        return None, None, None
    raw = str(site_ref).strip()
    if not raw:
        return None, None, None

    lower = raw.lower().strip()
    if lower.startswith("http://") or lower.startswith("https://"):
        parsed = urlparse(lower)
        host = (parsed.netloc or "").strip().lower()
    else:
        host = lower
        if "/" in host:
            host = host.split("/", 1)[0]

    deploy_domain = (os.getenv("DEPLOY_DOMAIN") or "").strip().lower()
    slug_candidate = None
    if host and deploy_domain and host.endswith("." + deploy_domain):
        slug_candidate = host[: -(len(deploy_domain) + 1)]
    elif _TENANT_RE.fullmatch(host):
        slug_candidate = host

    hostname_candidate = host if "." in host else None
    return raw, slug_candidate, hostname_candidate


def resolve_site_ref(user_id: str, site_ref: Optional[str] = None) -> dict[str, Any]:
    """
    Resolve a user site from flexible references:
    - UUID site_id
    - slug
    - hostname
    - full URL
    - special refs: default/current/active/latest (or empty)
    """
    special_default = {"default", "current", "active", "latest", ""}
    raw, slug_candidate, hostname_candidate = _normalize_site_ref(site_ref)
    ref_value = (raw or "").strip()
    is_default = (not ref_value) or (ref_value.lower() in special_default)

    if is_default:
        with _engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    select
                      s.id,
                      s.user_id,
                      s.project_name,
                      s.slug,
                      s.status,
                      s.updated_at,
                      d.hostname,
                      dep.id as active_deployment_id
                    from platform_sites s
                    left join platform_domains d
                      on d.site_id = s.id and d.is_primary = true
                    left join platform_deployments dep
                      on dep.site_id = s.id and dep.status = 'active'
                    where s.user_id = :user_id
                    order by (dep.id is not null) desc, s.updated_at desc
                    limit 1
                    """
                ),
                {"user_id": str(user_id)},
            ).mappings().first()
        if not row:
            raise ValueError("No sites found for this user")
        return dict(row)

    params = {
        "user_id": str(user_id),
        "ref_text": ref_value.lower(),
        "slug_candidate": slug_candidate,
        "hostname_candidate": hostname_candidate,
    }
    with _engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select
                  s.id,
                  s.user_id,
                  s.project_name,
                  s.slug,
                  s.status,
                  s.updated_at,
                  d.hostname,
                  dep.id as active_deployment_id
                from platform_sites s
                left join platform_domains d
                  on d.site_id = s.id and d.is_primary = true
                left join platform_deployments dep
                  on dep.site_id = s.id and dep.status = 'active'
                where
                  s.user_id = :user_id
                  and (
                    cast(s.id as text) = :ref_text
                    or s.slug = :ref_text
                    or lower(coalesce(d.hostname, '')) = :ref_text
                    or (:slug_candidate is not null and s.slug = :slug_candidate)
                    or (:hostname_candidate is not null and lower(coalesce(d.hostname, '')) = :hostname_candidate)
                    or lower(s.project_name) = :ref_text
                  )
                order by (dep.id is not null) desc, s.updated_at desc
                limit 1
                """
            ),
            params,
        ).mappings().first()

    if not row:
        raise ValueError(f"Could not resolve site from reference '{ref_value}'")
    return dict(row)


def list_user_sites(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 20), 100))
    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select
                  s.id as site_id,
                  s.project_name,
                  s.slug,
                  s.status,
                  s.created_at,
                  s.updated_at,
                  d.hostname,
                  dep.id as active_deployment_id,
                  dep.activated_at as active_deployment_activated_at,
                  db.turso_db_name as database_name
                from platform_sites s
                left join platform_domains d
                  on d.site_id = s.id and d.is_primary = true
                left join platform_deployments dep
                  on dep.site_id = s.id and dep.status = 'active'
                left join platform_site_databases db
                  on db.site_id = s.id
                where s.user_id = :user_id
                order by s.updated_at desc
                limit :lim
                """
            ),
            {"user_id": str(user_id), "lim": lim},
        ).mappings().all()
    return [dict(r) for r in rows]


def list_deployed_projects(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    List deployed projects for a user grouped by site, while preserving the
    full deployment/version history for each site.
    """
    lim = max(1, min(int(limit or 20), 100))
    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select
                  s.id as site_id,
                  s.project_name,
                  s.slug,
                  s.status as site_status,
                  s.updated_at,
                  d.hostname,
                  dep.id as deployment_id,
                  dep.version,
                  dep.r2_prefix,
                  dep.status as deployment_status,
                  dep.created_at as deployment_created_at,
                  dep.activated_at
                from platform_sites s
                join platform_deployments dep
                  on dep.site_id = s.id
                left join platform_domains d
                  on d.site_id = s.id and d.is_primary = true
                where s.user_id = :user_id
                order by s.updated_at desc, dep.version desc
                """
            ),
            {"user_id": str(user_id)},
        ).mappings().all()

    grouped: list[dict[str, Any]] = []
    by_site: dict[str, dict[str, Any]] = {}

    for row in rows:
        item = dict(row)
        site_id = str(item["site_id"])
        deployment = {
            "site_id": site_id,
            "project_name": item["project_name"],
            "slug": item["slug"],
            "site_status": item["site_status"],
            "hostname": item["hostname"],
            "deployment_id": item["deployment_id"],
            "version": item["version"],
            "r2_prefix": item["r2_prefix"],
            "deployment_status": item["deployment_status"],
            "deployment_created_at": item["deployment_created_at"],
            "activated_at": item["activated_at"],
            "updated_at": item["updated_at"],
        }

        project = by_site.get(site_id)
        if not project:
            project = {
                "site_id": site_id,
                "project_name": item["project_name"],
                "slug": item["slug"],
                "site_status": item["site_status"],
                "hostname": item["hostname"],
                "updated_at": item["updated_at"],
                "deployments": [],
            }
            by_site[site_id] = project
            grouped.append(project)

        project["deployments"].append(deployment)

    normalized: list[dict[str, Any]] = []
    for project in grouped[:lim]:
        deployments = list(project.get("deployments") or [])
        deployments.sort(
            key=lambda dep: (
                0 if str(dep.get("deployment_status") or "").lower() == "active" else 1,
                -(int(dep.get("version") or 0)),
            )
        )
        representative = deployments[0] if deployments else {}
        normalized.append(
            {
                **project,
                **representative,
                "deployments": deployments,
                "deployment_count": len(deployments),
            }
        )

    return normalized


def list_user_databases(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """
    List provisioned per-site databases owned by a user.
    Returns one row per site database with deployment/domain context when available.
    """
    lim = max(1, min(int(limit or 50), 200))
    with _engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                with latest_dep as (
                  select
                    d.site_id,
                    d.id as deployment_id,
                    d.status as deployment_status,
                    d.version,
                    d.r2_prefix,
                    row_number() over (
                      partition by d.site_id
                      order by (d.status = 'active') desc, d.version desc
                    ) as rn
                  from platform_deployments d
                )
                select
                  s.id as site_id,
                  s.project_name,
                  s.slug,
                  dm.hostname,
                  db.turso_db_name as database_name,
                  db.turso_db_hostname as database_hostname,
                  db.created_at as database_created_at,
                  dep.deployment_id,
                  dep.deployment_status,
                  dep.version,
                  dep.r2_prefix
                from platform_sites s
                join platform_site_databases db
                  on db.site_id = s.id
                left join platform_domains dm
                  on dm.site_id = s.id and dm.is_primary = true
                left join latest_dep dep
                  on dep.site_id = s.id and dep.rn = 1
                where s.user_id = :user_id
                order by db.created_at desc
                limit :lim
                """
            ),
            {"user_id": str(user_id), "lim": lim},
        ).mappings().all()
    return [dict(r) for r in rows]


def get_site_summary(site_id: str, user_id: str) -> dict[str, Any]:
    site = _ensure_site_owned(site_id=site_id, user_id=user_id)
    with _engine.connect() as conn:
        host_row = conn.execute(
            text(
                """
                select hostname
                from platform_domains
                where site_id = :site_id and is_primary = true
                """
            ),
            {"site_id": site_id},
        ).mappings().first()
    return {
        "site_id": site_id,
        "slug": site["slug"],
        "status": site["status"],
        "hostname": host_row["hostname"] if host_row else None,
    }


def get_deployment_summary(site_id: str, user_id: str, deployment_id: Optional[str] = None) -> dict[str, Any]:
    _ensure_site_owned(site_id=site_id, user_id=user_id)
    with _engine.connect() as conn:
        if deployment_id:
            row = conn.execute(
                text(
                    """
                    select id, site_id, version, r2_prefix, status, created_at, activated_at
                    from platform_deployments
                    where site_id = :site_id and id = :deployment_id
                    """
                ),
                {"site_id": site_id, "deployment_id": deployment_id},
            ).mappings().first()
        else:
            row = conn.execute(
                text(
                    """
                    select id, site_id, version, r2_prefix, status, created_at, activated_at
                    from platform_deployments
                    where site_id = :site_id
                    order by (status = 'active') desc, version desc
                    limit 1
                    """
                ),
                {"site_id": site_id},
            ).mappings().first()
    if not row:
        raise ValueError("Deployment not found")
    return dict(row)


def list_deployment_files(site_id: str, user_id: str, deployment_id: Optional[str] = None) -> list[dict[str, Any]]:
    dep = get_deployment_summary(site_id=site_id, user_id=user_id, deployment_id=deployment_id)
    prefix = str(dep["r2_prefix"]).rstrip("/") + "/"
    bucket = _require_env("R2_SITES_BUCKET")
    r2 = get_r2_client()

    files: list[dict[str, Any]] = []
    paginator = r2.client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    for page in pages:
        for obj in page.get("Contents", []) or []:
            key = str(obj.get("Key", ""))
            if not key or key.endswith("/"):
                continue
            rel_path = key[len(prefix):] if key.startswith(prefix) else key
            files.append(
                {
                    "path": rel_path,
                    "key": key,
                    "size": int(obj.get("Size", 0) or 0),
                    "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
                }
            )
    return files


def get_deployment_file_bytes(site_id: str, user_id: str, path: str, deployment_id: Optional[str] = None) -> bytes:
    dep = get_deployment_summary(site_id=site_id, user_id=user_id, deployment_id=deployment_id)
    rel = _sanitize_path(path)
    key = f"{str(dep['r2_prefix']).rstrip('/')}/{rel}"
    bucket = _require_env("R2_SITES_BUCKET")
    r2 = get_r2_client()
    response = r2.client.get_object(Bucket=bucket, Key=key)
    body = response.get("Body")
    data = body.read() if body else b""
    if data is None:
        return b""
    return data
