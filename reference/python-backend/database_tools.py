import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests
from agno.tools import Toolkit
from sqlalchemy import text

from deploy_platform import (
    _engine,
    ensure_deploy_tables,
    get_runtime_query_endpoint,
    get_site_db_credentials,
    provision_turso_database,
    resolve_site_ref,
)

logger = logging.getLogger(__name__)


class DatabaseTools(Toolkit):
    """
    Generic per-site database toolkit for deployed user apps.
    """

    def __init__(self, user_id: str):
        super().__init__(
            name="database_tools",
            tools=[
                self.create_database,
                self.run_query,
                self.migrate_database,
                self.delete_database,
                self.get_db_credentials,
            ],
        )
        self.user_id = str(user_id)
        self._selected_site_id: Optional[str] = None

    def _resolve_site(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Resolve a site from uuid/slug/domain/url/default and keep it as active selection.
        """
        ref = site_id or self._selected_site_id or "default"
        site = resolve_site_ref(user_id=self.user_id, site_ref=ref)
        self._selected_site_id = str(site["id"])
        return site

    def _db_record(self, site_id: str) -> Dict[str, Any]:
        with _engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    select turso_db_name, turso_db_hostname
                    from platform_site_databases
                    where site_id = :site_id
                    """
                ),
                {"site_id": str(site_id)},
            ).mappings().first()
        if not row:
            raise ValueError("No database provisioned for this site")
        return dict(row)

    def _to_hrana_value(self, value: Any) -> Dict[str, Any]:
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

    def _hrana_execute(self, hostname: str, token: str, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        args = [self._to_hrana_value(v) for v in (params or [])]
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": args,
                        "want_rows": True,
                    },
                }
            ]
        }
        url = f"https://{hostname}/v2/pipeline"
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Query failed: HTTP {response.status_code} {response.text}")

        data = response.json() or {}
        results = data.get("results") or []
        if not results:
            return {"raw": data}
        result = results[0] or {}
        if "error" in result:
            raise RuntimeError(f"Query failed: {result['error']}")
        return result.get("response", result)


    def create_database(self, site_id: Optional[str] = None) -> str:
        """
        Create and attach a dedicated database for the specified site.
        """
        try:
            ensure_deploy_tables()
            site = self._resolve_site(site_id=site_id)
            result = provision_turso_database(site_id=str(site["id"]), user_id=self.user_id)
            return json.dumps({"ok": True, **result}, ensure_ascii=True)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def run_query(self, sql: str, site_id: Optional[str] = None, params: Optional[List[Any]] = None) -> str:
        """
        Run a SQL query against the site's database.

        Notes:
        - Uses positional parameters for '?' placeholders.
        - Named parameters are not supported in this method.
        """
        try:
            ensure_deploy_tables()
            cleaned_sql = str(sql or "").strip()
            if not cleaned_sql:
                raise ValueError("sql is required")
            lowered = cleaned_sql.lower()
            if (
                "platform_sites" in lowered
                or "platform_deployments" in lowered
                or "platform_domains" in lowered
                or "platform_site_databases" in lowered
            ):
                raise ValueError(
                    "Platform tables are not queryable via run_query(). "
                    "Use deployed_project_tools methods to inspect deployed project metadata/files instead."
                )

            site = self._resolve_site(site_id=site_id)
            creds = get_site_db_credentials(site_id=str(site["id"]), user_id=self.user_id, include_admin=False)
            result = self._hrana_execute(
                hostname=creds["hostname"],
                token=creds["rw_token"],
                sql=cleaned_sql,
                params=params or [],
            )
            return json.dumps({"ok": True, "result": result}, ensure_ascii=True)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def migrate_database(self, migration_sql: str, site_id: Optional[str] = None) -> str:
        """
        Apply SQL migration statements to the site's database.
        """
        try:
            ensure_deploy_tables()
            raw = str(migration_sql or "").strip()
            if not raw:
                raise ValueError("migration_sql is required")
            statements = [part.strip() for part in raw.split(";") if part.strip()]
            if not statements:
                raise ValueError("No valid migration statements found")

            site = self._resolve_site(site_id=site_id)
            creds = get_site_db_credentials(site_id=str(site["id"]), user_id=self.user_id, include_admin=False)
            applied = 0
            for stmt in statements:
                self._hrana_execute(
                    hostname=creds["hostname"],
                    token=creds["rw_token"],
                    sql=stmt,
                    params=[],
                )
                applied += 1
            return json.dumps({"ok": True, "applied_statements": applied}, ensure_ascii=True)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def delete_database(self, site_id: Optional[str] = None) -> str:
        """
        Delete the site's database from provider and remove local metadata.
        """
        try:
            ensure_deploy_tables()
            site = self._resolve_site(site_id=site_id)
            db_row = self._db_record(str(site["id"]))

            org_slug = os.getenv("TURSO_ORG_SLUG")
            api_token = os.getenv("TURSO_API_TOKEN")
            if not org_slug or not api_token:
                raise ValueError("Missing TURSO_ORG_SLUG or TURSO_API_TOKEN")

            db_name = str(db_row["turso_db_name"])
            delete_url = f"https://api.turso.tech/v1/organizations/{org_slug}/databases/{db_name}"
            response = requests.delete(
                delete_url,
                headers={"Authorization": f"Bearer {api_token}"},
                timeout=30,
            )
            if response.status_code not in (200, 202, 204, 404):
                raise RuntimeError(f"Database delete failed: HTTP {response.status_code} {response.text}")

            with _engine.begin() as conn:
                conn.execute(
                    text("delete from platform_site_databases where site_id = :site_id"),
                    {"site_id": str(site["id"])},
                )

            return json.dumps({"ok": True, "deleted_database": db_name}, ensure_ascii=True)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def get_db_credentials(self, site_id: Optional[str] = None, include_secrets: bool = False) -> str:
        """
        Return runtime connection metadata for the site's database.
        By default, secrets are excluded to avoid exposing tokens in frontend code.
        """
        try:
            ensure_deploy_tables()
            site = self._resolve_site(site_id=site_id)
            creds = get_site_db_credentials(site_id=str(site["id"]), user_id=self.user_id, include_admin=False)
            safe_creds = {
                "database_name": creds["database_name"],
                "hostname": creds["hostname"],
                "url": creds["url"],
                "runtime_query_endpoint": get_runtime_query_endpoint(),
                "site_id": str(site["id"]),
                "site_slug": site.get("slug"),
                "site_hostname": site.get("hostname"),
            }
            if include_secrets:
                safe_creds["rw_token"] = creds.get("rw_token")
                safe_creds["ro_token"] = creds.get("ro_token")
            return json.dumps({"ok": True, "credentials": safe_creds}, ensure_ascii=True)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)
