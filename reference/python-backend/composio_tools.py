import json
import logging
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit

import config
from composio_client import ComposioApiError, ComposioClient

logger = logging.getLogger(__name__)


class _BaseComposioToolkit(Toolkit):
    TOOLKIT_SLUG = ""
    TOOLKIT_LABEL = ""

    def __init__(self, name: str, tools: List[callable], user_id: str):
        super().__init__(name=name, tools=tools)
        self.user_id = user_id
        self._client: Optional[ComposioClient] = None
        self._action_slug_set: Optional[set[str]] = None
        self._actions_listed = False

    def _get_client(self) -> ComposioClient:
        if self._client is None:
            self._client = ComposioClient()
        return self._client

    def _get_connected_account_id(self) -> Optional[str]:
        accounts = self._get_client().list_connected_accounts(user_id=self.user_id, toolkit_slug=self.TOOLKIT_SLUG)
        if not accounts:
            return None
        for account in accounts:
            if str(account.get("status", "")).upper() == "ACTIVE":
                return account.get("id")
        return accounts[0].get("id")

    def _list_actions_internal(self) -> List[Dict[str, Any]]:
        return self._get_client().list_tools(toolkit_slug=self.TOOLKIT_SLUG, important_only=True)

    def _format_actions(self, toolkit_label: str) -> str:
        try:
            tools = self._list_actions_internal()
            if not tools:
                self._action_slug_set = set()
                return f"No {toolkit_label} actions found from Composio."

            lines = []
            slug_set: set[str] = set()
            max_actions = 25
            for tool in tools[:max_actions]:
                slug = str(tool.get("slug", "UNKNOWN")).strip()
                slug_set.add(slug.upper())
                description = str(tool.get("description", "")).strip().replace("\n", " ")
                if len(description) > 120:
                    description = description[:117] + "..."
                lines.append(f"- {slug}: {description}".strip())
            self._action_slug_set = slug_set
            self._actions_listed = True
            return (
                f"Available {toolkit_label} actions (concise; use exact slug):\n"
                + "\n".join(lines)
            )
        except ComposioApiError as exc:
            logger.error("Composio list tools failed for %s: %s", self.TOOLKIT_SLUG, exc)
            return f"Failed to list {toolkit_label} actions: {exc}"

    def _parse_arguments(self, arguments_json: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            arguments: Dict[str, Any] = {}
            if arguments_json and arguments_json.strip():
                parsed = json.loads(arguments_json)
                if not isinstance(parsed, dict):
                    return None, "Error: arguments_json must decode to a JSON object."
                arguments = parsed
            return arguments, None
        except json.JSONDecodeError as exc:
            return None, f"Error: invalid arguments_json. {exc}"

    def _validate_or_suggest_slug(self, tool_slug: str, toolkit_label: str) -> Optional[str]:
        requested = tool_slug.strip().upper()
        if not self._actions_listed:
            return (
                f"Error: call list_{toolkit_label.lower().replace(' ', '_')}_actions() first in this run, "
                "then execute using an exact returned slug."
            )
        if not self._action_slug_set:
            return f"Error: no {toolkit_label} actions are currently available."
        if requested in self._action_slug_set:
            return requested
        return (
            f"Error: '{tool_slug}' is not a valid {toolkit_label} action slug for this account. "
            f"Call list_{toolkit_label.lower().replace(' ', '_')}_actions() first and use one of those exact slugs."
        )


class ComposioGoogleSheetsTools(_BaseComposioToolkit):
    """
    Agno toolkit wrapper for Composio Google Sheets actions.
    """

    TOOLKIT_SLUG = "GOOGLESHEETS"
    TOOLKIT_LABEL = "Google Sheets"

    def __init__(self, user_id: str):
        super().__init__(
            name="composio_google_sheets_tools",
            tools=[self.list_google_sheets_actions, self.execute_google_sheets_action],
            user_id=user_id,
        )

    def list_google_sheets_actions(self) -> str:
        return self._format_actions(self.TOOLKIT_LABEL)

    def execute_google_sheets_action(self, tool_slug: str, arguments_json: str = "{}") -> str:
        if not tool_slug:
            return "Error: tool_slug is required."

        arguments, error = self._parse_arguments(arguments_json)
        if error:
            return error

        normalized_or_error = self._validate_or_suggest_slug(tool_slug, self.TOOLKIT_LABEL)
        if normalized_or_error is None:
            return "Error: unable to validate tool slug."
        if normalized_or_error.startswith("Error:"):
            return normalized_or_error
        normalized_slug = normalized_or_error

        try:
            connected_account_id = self._get_connected_account_id()
            if not connected_account_id:
                callback_hint = config.FRONTEND_URL or "your frontend URL"
                return (
                    "Google Sheets is not connected in Composio. "
                    "Use /api/composio/connect-url?toolkit=GOOGLESHEETS to generate a connect link "
                    f"and complete auth, then retry. Callback URL should be {callback_hint}."
                )

            result = self._get_client().execute_tool(
                tool_slug=normalized_slug,
                connected_account_id=connected_account_id,
                user_id=self.user_id,
                entity_id=self.user_id,
                arguments=arguments or {},
            )
            return json.dumps(result, ensure_ascii=True, indent=2)
        except ComposioApiError as exc:
            logger.error("Composio execute failed for %s: %s", normalized_slug, exc)
            return f"Failed to execute '{normalized_slug}': {exc}"


class ComposioWhatsAppTools(_BaseComposioToolkit):
    """
    Agno toolkit wrapper for Composio WhatsApp actions.
    """

    TOOLKIT_SLUG = "WHATSAPP"
    TOOLKIT_LABEL = "WhatsApp"

    def __init__(self, user_id: str):
        super().__init__(
            name="composio_whatsapp_tools",
            tools=[self.list_whatsapp_actions, self.execute_whatsapp_action],
            user_id=user_id,
        )

    def list_whatsapp_actions(self) -> str:
        return self._format_actions(self.TOOLKIT_LABEL)

    def execute_whatsapp_action(self, tool_slug: str, arguments_json: str = "{}") -> str:
        if not tool_slug:
            return "Error: tool_slug is required."

        arguments, error = self._parse_arguments(arguments_json)
        if error:
            return error

        normalized_or_error = self._validate_or_suggest_slug(tool_slug, self.TOOLKIT_LABEL)
        if normalized_or_error is None:
            return "Error: unable to validate tool slug."
        if normalized_or_error.startswith("Error:"):
            return normalized_or_error
        normalized_slug = normalized_or_error

        try:
            connected_account_id = self._get_connected_account_id()
            if not connected_account_id:
                callback_hint = config.FRONTEND_URL or "your frontend URL"
                return (
                    "WhatsApp is not connected in Composio. "
                    "Use /api/composio/connect-url?toolkit=WHATSAPP to generate a connect link "
                    f"and complete auth, then retry. Callback URL should be {callback_hint}."
                )

            result = self._get_client().execute_tool(
                tool_slug=normalized_slug,
                connected_account_id=connected_account_id,
                user_id=self.user_id,
                entity_id=self.user_id,
                arguments=arguments or {},
            )
            return json.dumps(result, ensure_ascii=True, indent=2)
        except ComposioApiError as exc:
            logger.error("Composio execute failed for %s: %s", normalized_slug, exc)
            return f"Failed to execute '{normalized_slug}': {exc}"


def has_active_google_sheets_connection(user_id: str) -> bool:
    try:
        client = ComposioClient()
        accounts = client.list_connected_accounts(
            user_id=user_id,
            toolkit_slug=ComposioGoogleSheetsTools.TOOLKIT_SLUG,
            statuses=["ACTIVE"],
        )
        return len(accounts) > 0
    except Exception as exc:
        logger.warning("Failed to verify Composio Google Sheets connection for user %s: %s", user_id, exc)
        return False


def has_active_whatsapp_connection(user_id: str) -> bool:
    try:
        client = ComposioClient()
        accounts = client.list_connected_accounts(
            user_id=user_id,
            toolkit_slug=ComposioWhatsAppTools.TOOLKIT_SLUG,
            statuses=["ACTIVE"],
        )
        return len(accounts) > 0
    except Exception as exc:
        logger.warning("Failed to verify Composio WhatsApp connection for user %s: %s", user_id, exc)
        return False
