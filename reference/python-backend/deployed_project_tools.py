import json
import logging
from typing import Any, Dict, Optional

from agno.tools import Toolkit

from deploy_platform import (
    ensure_deploy_tables,
    get_deployment_file_bytes,
    get_deployment_summary,
    get_site_summary,
    list_deployed_projects,
    list_deployment_files,
    resolve_site_ref,
)

logger = logging.getLogger(__name__)


class DeployedProjectTools(Toolkit):
    """
    Toolkit for deployed project discovery and source retrieval.
    """

    def __init__(self, user_id: str):
        super().__init__(
            name="deployed_project_tools",
            tools=[
                self.get_deployed_projects,
                self.select_project,
                self.get_deployment,
                self.get_file_structure,
                self.get_file_content,
            ],
        )
        self.user_id = str(user_id)
        self._selected_site_id: Optional[str] = None

    def _resolve_site(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        ref = site_id or self._selected_site_id or "default"
        site = resolve_site_ref(user_id=self.user_id, site_ref=ref)
        self._selected_site_id = str(site["id"])
        return site

    def get_deployed_projects(self, limit: int = 20) -> str:
        """
        List deployed projects for this user.
        Returns one representative deployment per site (active preferred).
        """
        try:
            ensure_deploy_tables()
            projects = list_deployed_projects(user_id=self.user_id, limit=limit)
            return json.dumps({"ok": True, "projects": projects}, ensure_ascii=True, default=str)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def select_project(self, site_id: str = "default") -> str:
        """
        Select project context by site_id/slug/hostname/url/default.
        """
        try:
            ensure_deploy_tables()
            site = self._resolve_site(site_id=site_id)
            return json.dumps(
                {
                    "ok": True,
                    "selected_site_id": str(site["id"]),
                    "slug": site.get("slug"),
                    "hostname": site.get("hostname"),
                },
                ensure_ascii=True,
                default=str,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def get_deployment(self, site_id: Optional[str] = None, deployment_id: Optional[str] = None) -> str:
        """
        Get deployment details for selected project/site.
        """
        try:
            ensure_deploy_tables()
            site = self._resolve_site(site_id=site_id)
            dep = get_deployment_summary(
                site_id=str(site["id"]),
                user_id=self.user_id,
                deployment_id=deployment_id,
            )
            return json.dumps(
                {
                    "ok": True,
                    "site_id": str(site["id"]),
                    "slug": site.get("slug"),
                    "hostname": site.get("hostname"),
                    "deployment": dep,
                },
                ensure_ascii=True,
                default=str,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def get_file_structure(self, site_id: Optional[str] = None, deployment_id: Optional[str] = None) -> str:
        """
        Get deployed file structure for selected project/site.
        """
        try:
            ensure_deploy_tables()
            site = self._resolve_site(site_id=site_id)
            dep = get_deployment_summary(
                site_id=str(site["id"]),
                user_id=self.user_id,
                deployment_id=deployment_id,
            )
            files = list_deployment_files(
                site_id=str(site["id"]),
                user_id=self.user_id,
                deployment_id=dep["id"],
            )
            return json.dumps(
                {
                    "ok": True,
                    "site_id": str(site["id"]),
                    "slug": site.get("slug"),
                    "hostname": site.get("hostname"),
                    "deployment_id": dep["id"],
                    "r2_prefix": dep.get("r2_prefix"),
                    "file_count": len(files),
                    "files": [{"path": f["path"], "size": f["size"]} for f in files],
                },
                ensure_ascii=True,
                default=str,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def get_file_content(
        self,
        path: str,
        site_id: Optional[str] = None,
        deployment_id: Optional[str] = None,
        max_chars: int = 20000,
    ) -> str:
        """
        Get file content from deployed project.
        """
        try:
            ensure_deploy_tables()
            if not str(path or "").strip():
                raise ValueError("path is required")
            site = self._resolve_site(site_id=site_id)
            dep = get_deployment_summary(
                site_id=str(site["id"]),
                user_id=self.user_id,
                deployment_id=deployment_id,
            )
            data = get_deployment_file_bytes(
                site_id=str(site["id"]),
                user_id=self.user_id,
                path=path,
                deployment_id=dep["id"],
            )
            text_content = data.decode("utf-8", errors="replace")
            lim = max(500, min(int(max_chars or 20000), 200000))
            truncated = text_content[:lim]
            return json.dumps(
                {
                    "ok": True,
                    "site_id": str(site["id"]),
                    "deployment_id": dep["id"],
                    "path": path,
                    "size_bytes": len(data),
                    "truncated": len(text_content) > len(truncated),
                    "content": truncated,
                },
                ensure_ascii=True,
                default=str,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)
