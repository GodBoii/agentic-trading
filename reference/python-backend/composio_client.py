import json
import logging
from typing import Any, Dict, List, Optional

import requests

import config

logger = logging.getLogger(__name__)


class ComposioApiError(Exception):
    """Raised when Composio API returns an error."""


class ComposioClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.api_key = api_key or config.COMPOSIO_API_KEY
        self.base_url = (base_url or config.COMPOSIO_BASE_URL).rstrip("/")
        self.project_id = project_id or config.COMPOSIO_PROJECT_ID
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise ComposioApiError("COMPOSIO_API_KEY is not configured.")

    def _headers(self) -> Dict[str, str]:
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.project_id:
            headers["x-composio-project-id"] = self.project_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._headers(),
                params=params,
                json=json_payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ComposioApiError(f"Failed to reach Composio API: {exc}") from exc

        if not response.ok:
            body = response.text
            try:
                parsed = response.json()
                body = parsed.get("message") or parsed.get("error") or json.dumps(parsed)
            except Exception:
                pass
            raise ComposioApiError(f"Composio API error ({response.status_code}): {body}")

        if response.status_code == 204 or not response.text:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise ComposioApiError("Composio API returned non-JSON response.") from exc

    def list_tools(self, toolkit_slug: str, important_only: bool = True) -> List[Dict[str, Any]]:
        params = {
            "toolkit_slug": toolkit_slug,
            "limit": 100,
        }
        if important_only:
            params["important"] = "true"
        result = self._request("GET", "/tools", params=params)
        return result.get("items", []) if isinstance(result, dict) else []

    def list_connected_accounts(
        self,
        user_id: str,
        toolkit_slug: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"user_ids": user_id, "limit": 100}
        if toolkit_slug:
            params["toolkit_slugs"] = toolkit_slug
        if statuses:
            params["statuses"] = ",".join(statuses)
        result = self._request("GET", "/connected_accounts", params=params)
        return result.get("items", []) if isinstance(result, dict) else []

    def create_connected_account_link(
        self,
        user_id: str,
        auth_config_id: str,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "auth_config_id": auth_config_id,
        }
        if callback_url:
            payload["callback_url"] = callback_url
        return self._request("POST", "/connected_accounts/link", json_payload=payload)

    def execute_tool(
        self,
        tool_slug: str,
        connected_account_id: str,
        user_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "connected_account_id": connected_account_id,
            "user_id": user_id,
            "entity_id": entity_id,
            "arguments": arguments or {},
        }
        return self._request("POST", f"/tools/execute/{tool_slug}", json_payload=payload)

    def delete_connected_account(self, connected_account_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/connected_accounts/{connected_account_id}")
