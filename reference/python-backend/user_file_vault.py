import base64
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Optional

import requests

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_DB_NAME_RE = re.compile(r"^[a-z0-9-]{3,64}$")

_VAULT_STATE: dict[str, str] = {}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _require_env(name: str) -> str:
    val = (os.getenv(name) or "").strip()
    if not val:
        raise ValueError(f"Missing required environment variable: {name}")
    return val


def _safe_db_name(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]", "-", str(raw or "").lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if len(cleaned) < 3:
        cleaned = f"vault-{cleaned}".strip("-")
    if len(cleaned) > 64:
        cleaned = cleaned[:64].rstrip("-")
    if not _DB_NAME_RE.fullmatch(cleaned):
        raise ValueError("Invalid Turso vault DB name")
    return cleaned


def _sanitize_filename(file_name: str) -> str:
    raw = str(file_name or "").strip().replace("\\", "/")
    raw = raw.split("/")[-1]
    if not raw:
        raise ValueError("fileName is required")
    cleaned = _SAFE_NAME_RE.sub("_", raw)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        raise ValueError("Invalid fileName")
    return cleaned[:180]


def _to_hrana_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (dict, list)):
        return {"type": "text", "value": json.dumps(value, ensure_ascii=True)}
    return {"type": "text", "value": str(value)}


def _from_hrana_row(row: list[Any], columns: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for idx, col in enumerate(columns):
        cell = row[idx] if idx < len(row) else None
        if not isinstance(cell, dict):
            out[col] = None
            continue
        ctype = cell.get("type")
        if ctype == "null":
            out[col] = None
        elif ctype == "integer":
            raw = cell.get("value")
            try:
                out[col] = int(raw) if raw is not None else 0
            except Exception:
                out[col] = raw
        elif ctype == "float":
            out[col] = cell.get("value")
        else:
            out[col] = cell.get("value")
    return out


def _extract_result_rows(result: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    payload = result or {}
    # Hrana execute responses can be either:
    # - {"cols": [...], "rows": [...]}
    # - {"result": {"cols": [...], "rows": [...]}}
    if isinstance(payload.get("result"), dict):
        payload = payload.get("result") or {}

    cols_raw = (payload or {}).get("cols") or []
    rows = (payload or {}).get("rows") or []
    col_names: list[str] = []
    for col in cols_raw:
        if isinstance(col, dict):
            col_names.append(str(col.get("name") or ""))
        else:
            col_names.append(str(col))
    return col_names, rows


def _ensure_vault_state() -> dict[str, str]:
    if _VAULT_STATE.get("hostname") and _VAULT_STATE.get("token") and _VAULT_STATE.get("db_name"):
        return _VAULT_STATE

    org_slug = _require_env("TURSO_ORG_SLUG")
    group = _require_env("TURSO_GROUP")
    api_token = _require_env("TURSO_API_TOKEN")
    db_name = _safe_db_name(os.getenv("TURSO_FILE_VAULT_DB") or "aetheria-user-files")

    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    base = f"https://api.turso.tech/v1/organizations/{org_slug}/databases"

    # Best-effort create (idempotent if already exists).
    try:
        create_resp = requests.post(base, headers=headers, json={"name": db_name, "group": group}, timeout=30)
        if create_resp.status_code not in (200, 201, 409):
            txt = (create_resp.text or "")[:300]
            raise RuntimeError(f"Turso vault DB create failed: HTTP {create_resp.status_code} {txt}")
    except Exception as exc:
        if "409" not in str(exc):
            raise

    hostname = (os.getenv("TURSO_FILE_VAULT_HOSTNAME") or "").strip()
    if not hostname:
        hostname = f"{db_name}-{org_slug}.turso.io"

    token = (os.getenv("TURSO_FILE_VAULT_TOKEN") or "").strip()
    if not token:
        token_resp = requests.post(
            f"{base}/{db_name}/auth/tokens?authorization=full-access&expiration=365d",
            headers=headers,
            timeout=30,
        )
        if token_resp.status_code not in (200, 201):
            txt = (token_resp.text or "")[:300]
            raise RuntimeError(f"Turso vault token create failed: HTTP {token_resp.status_code} {txt}")
        token = (token_resp.json() or {}).get("jwt") or ""
        if not token:
            raise RuntimeError("Turso vault token response missing jwt")

    _VAULT_STATE["hostname"] = hostname
    _VAULT_STATE["token"] = token
    _VAULT_STATE["db_name"] = db_name
    return _VAULT_STATE


def _execute_hrana(sql: str, params: Optional[list[Any]] = None, want_rows: bool = True) -> dict[str, Any]:
    state = _ensure_vault_state()
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": str(sql),
                    "args": [_to_hrana_value(v) for v in (params or [])],
                    "want_rows": bool(want_rows),
                },
            }
        ]
    }
    resp = requests.post(
        f"https://{state['hostname']}/v2/pipeline",
        headers={"Authorization": f"Bearer {state['token']}", "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    if resp.status_code not in (200, 201):
        txt = (resp.text or "")[:400]
        raise RuntimeError(f"Turso query failed: HTTP {resp.status_code} {txt}")

    data = resp.json() or {}
    results = data.get("results") or []
    if not results:
        return {}
    first = results[0] or {}
    if "error" in first:
        raise RuntimeError(f"Turso query error: {first['error']}")
    return first.get("response", first)


def ensure_user_file_tables() -> None:
    _execute_hrana(
        """
        create table if not exists user_file_vault (
          id text primary key,
          user_id text not null,
          file_name text not null,
          mime_type text,
          size_bytes integer not null default 0,
          tags_text text not null default '[]',
          content_base64 text not null,
          created_at text not null,
          updated_at text not null
        )
        """,
        want_rows=False,
    )
    _execute_hrana(
        "create index if not exists idx_user_file_vault_user_created on user_file_vault(user_id, created_at desc)",
        want_rows=False,
    )


def create_user_file_upload_link(
    *,
    user_id: str,
    file_name: str,
    mime_type: Optional[str] = None,
    size_bytes: Optional[int] = None,
) -> dict[str, Any]:
    ensure_user_file_tables()
    safe_name = _sanitize_filename(file_name)
    return {
        "bucket": _ensure_vault_state()["db_name"],
        "path": f"{user_id}/vault/{uuid.uuid4()}/{safe_name}",
        "upload_url": None,
        "file_name": safe_name,
        "mime_type": str(mime_type or "application/octet-stream"),
        "size_bytes": int(size_bytes or 0),
        "created_at": _utc_now_iso(),
    }


def register_user_file(
    *,
    user_id: str,
    path: str,
    file_name: Optional[str] = None,
    mime_type: Optional[str] = None,
    size_bytes: Optional[int] = None,
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    _ = (path, size_bytes)
    raise ValueError("Direct register flow is no longer used. Use /api/user-files/upload with contentBase64.")


def upload_user_file_from_base64(
    *,
    user_id: str,
    file_name: str,
    mime_type: Optional[str],
    content_base64: str,
    size_bytes: Optional[int] = None,
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    ensure_user_file_tables()
    safe_name = _sanitize_filename(file_name)
    now_iso = _utc_now_iso()
    file_id = str(uuid.uuid4())
    clean_tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:20]

    # Validate base64 payload early.
    raw = base64.b64decode(str(content_base64 or "").encode("utf-8"), validate=False)
    computed_size = len(raw)
    if computed_size <= 0:
        raise ValueError("contentBase64 is empty")

    _execute_hrana(
        """
        insert into user_file_vault (
          id, user_id, file_name, mime_type, size_bytes, tags_text, content_base64, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        params=[
            file_id,
            str(user_id),
            safe_name,
            str(mime_type or "application/octet-stream"),
            int(size_bytes or computed_size),
            json.dumps(clean_tags, ensure_ascii=True),
            str(content_base64),
            now_iso,
            now_iso,
        ],
        want_rows=False,
    )

    return {
        "id": file_id,
        "user_id": str(user_id),
        "storage_bucket": _ensure_vault_state()["db_name"],
        "storage_path": f"turso://{_ensure_vault_state()['db_name']}/{file_id}",
        "file_name": safe_name,
        "mime_type": str(mime_type or "application/octet-stream"),
        "size_bytes": int(size_bytes or computed_size),
        "tags": clean_tags,
        "created_at": now_iso,
        "download_url": None,
    }


def _list_rows(*, user_id: str, limit: int, search: str = "", file_type: str = "all") -> list[dict[str, Any]]:
    ensure_user_file_tables()
    lim = int(max(1, min(limit, 500)))
    query = (
        "select id, user_id, file_name, mime_type, size_bytes, tags_text, created_at "
        "from user_file_vault where user_id = ?"
    )
    params: list[Any] = [str(user_id)]

    if search:
        query += " and (lower(file_name) like ? )"
        params.append(f"%{search.lower()}%")

    normalized_type = str(file_type or "all").strip().lower()
    if normalized_type and normalized_type != "all":
        query += " and lower(substr(coalesce(mime_type,''),1,instr(coalesce(mime_type,''),'/')-1)) = ?"
        params.append(normalized_type)

    query += " order by created_at desc limit ?"
    params.append(lim)

    resp = _execute_hrana(query, params=params, want_rows=True)
    cols, rows = _extract_result_rows(resp)
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _from_hrana_row(row, cols)
        try:
            item["tags"] = json.loads(item.get("tags_text") or "[]")
        except Exception:
            item["tags"] = []
        item["storage_bucket"] = _ensure_vault_state()["db_name"]
        item["storage_path"] = f"turso://{_ensure_vault_state()['db_name']}/{item.get('id')}"
        item["download_url"] = None
        out.append(item)
    return out


def list_user_files(
    *,
    user_id: str,
    limit: int = 100,
    search: str = "",
    file_type: str = "all",
    signed_url_expiry: int = 3600,
) -> list[dict[str, Any]]:
    _ = signed_url_expiry
    return _list_rows(user_id=user_id, limit=limit, search=search, file_type=file_type)


def get_user_file(*, user_id: str, file_id: str, include_signed_url: bool = True, signed_url_expiry: int = 3600) -> dict[str, Any]:
    _ = (include_signed_url, signed_url_expiry)
    ensure_user_file_tables()
    resp = _execute_hrana(
        "select id, user_id, file_name, mime_type, size_bytes, tags_text, created_at from user_file_vault where id = ? and user_id = ? limit 1",
        params=[str(file_id), str(user_id)],
        want_rows=True,
    )
    cols, rows = _extract_result_rows(resp)
    if not rows:
        raise ValueError("File not found")
    item = _from_hrana_row(rows[0], cols)
    try:
        item["tags"] = json.loads(item.get("tags_text") or "[]")
    except Exception:
        item["tags"] = []
    item["storage_bucket"] = _ensure_vault_state()["db_name"]
    item["storage_path"] = f"turso://{_ensure_vault_state()['db_name']}/{item.get('id')}"
    item["download_url"] = None
    return item


def delete_user_file(*, user_id: str, file_id: str) -> dict[str, Any]:
    file_row = get_user_file(user_id=user_id, file_id=file_id, include_signed_url=False)
    _execute_hrana(
        "delete from user_file_vault where id = ? and user_id = ?",
        params=[str(file_id), str(user_id)],
        want_rows=False,
    )
    return {
        "deleted": True,
        "id": str(file_id),
        "file_name": file_row.get("file_name"),
        "storage_path": file_row.get("storage_path"),
    }


def read_user_file_text(*, user_id: str, file_id: str, max_chars: int = 40000) -> dict[str, Any]:
    ensure_user_file_tables()
    resp = _execute_hrana(
        "select id, file_name, mime_type, size_bytes, content_base64 from user_file_vault where id = ? and user_id = ? limit 1",
        params=[str(file_id), str(user_id)],
        want_rows=True,
    )
    cols, rows = _extract_result_rows(resp)
    if not rows:
        raise ValueError("File not found")
    row = _from_hrana_row(rows[0], cols)

    data = base64.b64decode(str(row.get("content_base64") or "").encode("utf-8"), validate=False)
    is_binary = b"\x00" in data
    if is_binary:
        return {
            "id": row.get("id"),
            "file_name": row.get("file_name"),
            "mime_type": row.get("mime_type"),
            "size_bytes": int(row.get("size_bytes") or len(data)),
            "is_binary": True,
            "content": None,
            "download_url": None,
        }

    text_data = data.decode("utf-8", errors="replace")
    limit = max(200, min(int(max_chars or 40000), 200000))
    snippet = text_data[:limit]
    return {
        "id": row.get("id"),
        "file_name": row.get("file_name"),
        "mime_type": row.get("mime_type"),
        "size_bytes": int(row.get("size_bytes") or len(data)),
        "is_binary": False,
        "truncated": len(text_data) > len(snippet),
        "content": snippet,
        "download_url": None,
    }


def get_user_file_bytes(*, user_id: str, file_id: str) -> tuple[dict[str, Any], bytes]:
    ensure_user_file_tables()
    resp = _execute_hrana(
        "select id, file_name, mime_type, size_bytes, content_base64 from user_file_vault where id = ? and user_id = ? limit 1",
        params=[str(file_id), str(user_id)],
        want_rows=True,
    )
    cols, rows = _extract_result_rows(resp)
    if not rows:
        raise ValueError("File not found")
    row = _from_hrana_row(rows[0], cols)
    data = base64.b64decode(str(row.get("content_base64") or "").encode("utf-8"), validate=False)
    meta = {
        "id": row.get("id"),
        "file_name": row.get("file_name"),
        "mime_type": row.get("mime_type") or "application/octet-stream",
        "size_bytes": int(row.get("size_bytes") or len(data)),
    }
    return meta, data
