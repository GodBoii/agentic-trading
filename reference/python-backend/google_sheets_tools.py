import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from agno.tools import Toolkit
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from supabase_client import supabase_client

logger = logging.getLogger(__name__)


class GoogleSheetsTools(Toolkit):
    """Toolkit for native Google Sheets operations with frontend-friendly preview metadata."""

    _SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"
    _SPREADSHEET_URL_TEMPLATE = "https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    def __init__(self, user_id: str):
        super().__init__(
            name="google_sheets_tools",
            tools=[
                self.search_spreadsheets,
                self.get_spreadsheet_info,
                self.list_sheet_titles,
                self.read_range,
                self.batch_read_ranges,
                self.write_range,
                self.append_rows,
                self.batch_write_ranges,
                self.clear_range,
                self.add_sheet,
                self.rename_sheet,
                self.delete_sheet,
                self.create_spreadsheet,
            ],
        )
        self.user_id = user_id
        self._credentials: Optional[Credentials] = None
        self._sheets_service: Optional[Resource] = None
        self._drive_service: Optional[Resource] = None

    # ---------------------------------------------------------------------
    # Auth / service helpers
    # ---------------------------------------------------------------------
    def _get_credentials(self) -> Optional[Credentials]:
        if self._credentials and self._credentials.valid:
            return self._credentials

        try:
            response = (
                supabase_client.from_("user_integrations")
                .select("access_token, refresh_token, scopes")
                .eq("user_id", self.user_id)
                .eq("service", "google")
                .single()
                .execute()
            )
            if not response.data:
                logger.info("No Google integration found for user=%s", self.user_id)
                return None

            creds_data = response.data
            creds = Credentials(
                token=creds_data.get("access_token"),
                refresh_token=creds_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=creds_data.get("scopes"),
            )

            if creds.expired:
                if not creds.refresh_token:
                    logger.warning("Google credentials expired with no refresh token for user=%s", self.user_id)
                    return None
                creds.refresh(Request())
                supabase_client.from_("user_integrations").update(
                    {
                        "access_token": creds.token,
                        "scopes": creds.scopes,
                    }
                ).eq("user_id", self.user_id).eq("service", "google").execute()

            self._credentials = creds
            return self._credentials
        except Exception as exc:
            logger.error(
                "Error fetching/refreshing Google credentials for user %s: %s",
                self.user_id,
                exc,
                exc_info=True,
            )
            return None

    def _get_sheets_service(self) -> Optional[Resource]:
        if self._sheets_service:
            return self._sheets_service
        credentials = self._get_credentials()
        if not credentials:
            return None
        try:
            self._sheets_service = build("sheets", "v4", credentials=credentials)
            return self._sheets_service
        except HttpError as error:
            logger.error("Failed to build Google Sheets service: %s", error)
            return None

    def _get_drive_service(self) -> Optional[Resource]:
        if self._drive_service:
            return self._drive_service
        credentials = self._get_credentials()
        if not credentials:
            return None
        try:
            self._drive_service = build("drive", "v3", credentials=credentials)
            return self._drive_service
        except HttpError as error:
            logger.error("Failed to build Google Drive service: %s", error)
            return None

    # ---------------------------------------------------------------------
    # Output helpers
    # ---------------------------------------------------------------------
    def _respond(self, ok: bool, message: str, data: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        payload: Dict[str, Any] = {
            "ok": ok,
            "message": message,
            "data": data or {},
        }
        if metadata:
            payload["metadata"] = metadata
        return json.dumps(payload, ensure_ascii=False)

    def _error_response(self, action: str, message: str, *, spreadsheet_id: Optional[str] = None, spreadsheet_url: Optional[str] = None) -> str:
        metadata = self._build_metadata(
            action=action,
            preview_type="text",
            title="Google Sheets operation failed",
            summary=message,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_url=spreadsheet_url,
            inline={"error": message},
            status="error",
        )
        return self._respond(False, message, data={"action": action}, metadata=metadata)

    def _build_metadata(
        self,
        *,
        action: str,
        preview_type: str,
        title: str,
        summary: str,
        spreadsheet_id: Optional[str] = None,
        spreadsheet_url: Optional[str] = None,
        sheet_title: Optional[str] = None,
        range_name: Optional[str] = None,
        inline: Optional[Dict[str, Any]] = None,
        operation: Optional[str] = None,
        status: str = "success",
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "kind": "google_sheets_tool_output",
            "output_id": f"sheets-{uuid.uuid4().hex}",
            "action": action,
            "preview_type": preview_type,
            "title": title,
            "summary": summary,
            "status": status,
        }
        if spreadsheet_id:
            metadata["spreadsheet_id"] = spreadsheet_id
            metadata["spreadsheet_url"] = spreadsheet_url or self._sheet_url(spreadsheet_id)
        elif spreadsheet_url:
            metadata["spreadsheet_url"] = spreadsheet_url
        if sheet_title:
            metadata["sheet_title"] = sheet_title
        if range_name:
            metadata["range"] = range_name
        if inline:
            metadata["inline"] = inline
        if operation:
            metadata["operation"] = operation
        return metadata

    def _http_error_message(self, error: HttpError) -> str:
        try:
            raw_content = getattr(error, "content", None)
            if raw_content:
                decoded = raw_content.decode("utf-8", errors="replace")
                payload = json.loads(decoded)
                details = payload.get("error", {})
                message = details.get("message")
                if message:
                    return message
            return str(error)
        except Exception:
            return str(error)

    # ---------------------------------------------------------------------
    # Parsing / normalization helpers
    # ---------------------------------------------------------------------
    def _extract_spreadsheet_id(self, spreadsheet_id_or_url: str) -> str:
        value = str(spreadsheet_id_or_url or "").strip()
        if not value:
            return ""
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
        if match:
            return match.group(1)
        return value

    def _sheet_url(self, spreadsheet_id: str) -> str:
        return self._SPREADSHEET_URL_TEMPLATE.format(spreadsheet_id=spreadsheet_id)

    def _escape_drive_query(self, value: str) -> str:
        return str(value or "").replace("\\", "\\\\").replace("'", "\\'")

    def _parse_json_input(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, (int, float, bool)):
            return value
        text = str(value).strip()
        if not text:
            return None
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value

    def _normalize_values(self, values_json: Any) -> List[List[Any]]:
        parsed = self._parse_json_input(values_json)

        if parsed is None:
            return []

        if isinstance(parsed, dict):
            if "values" in parsed:
                parsed = parsed.get("values")
            elif "rows" in parsed:
                parsed = parsed.get("rows")

        if isinstance(parsed, list):
            if not parsed:
                return []
            if all(not isinstance(item, list) for item in parsed):
                return [parsed]
            return [item if isinstance(item, list) else [item] for item in parsed]

        return [[parsed]]

    def _normalize_ranges(self, ranges_input: Any) -> List[str]:
        parsed = self._parse_json_input(ranges_input)

        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

        if isinstance(parsed, str):
            text = parsed.strip()
            if not text:
                return []
            if "," in text:
                return [part.strip() for part in text.split(",") if part.strip()]
            return [text]

        return []

    def _normalize_batch_updates(self, updates_json: Any) -> List[Dict[str, Any]]:
        parsed = self._parse_json_input(updates_json)

        if isinstance(parsed, dict):
            parsed = parsed.get("data", parsed.get("updates", []))
        if not isinstance(parsed, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            range_name = str(item.get("range") or "").strip()
            values = self._normalize_values(item.get("values"))
            if range_name and values:
                normalized.append({"range": range_name, "values": values})
        return normalized

    def _build_table_inline(self, values: List[List[Any]], range_name: Optional[str] = None) -> Dict[str, Any]:
        total_rows = len(values)
        total_columns = max((len(row) for row in values), default=0)
        preview_rows = values[:10]

        columns: List[str] = []
        rows: List[List[str]] = []
        if preview_rows:
            maybe_header = preview_rows[0]
            if any(str(cell).strip() for cell in maybe_header):
                columns = [str(cell) for cell in maybe_header]
                rows = [[str(cell) for cell in row] for row in preview_rows[1:]]
            else:
                rows = [[str(cell) for cell in row] for row in preview_rows]

        if not columns:
            columns = [f"Column {index + 1}" for index in range(total_columns)]

        return {
            "columns": columns,
            "rows": rows,
            "row_count": total_rows,
            "column_count": total_columns,
            "truncated": total_rows > len(preview_rows),
            "range": range_name,
        }

    def _get_sheet_map(self, spreadsheet: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for sheet in spreadsheet.get("sheets", []) or []:
            props = sheet.get("properties", {}) or {}
            title = str(props.get("title") or "").strip()
            if title:
                result[title] = props
        return result

    # ---------------------------------------------------------------------
    # Tools
    # ---------------------------------------------------------------------
    def search_spreadsheets(self, query: str, max_results: int = 10) -> str:
        service = self._get_drive_service()
        if not service:
            return self._error_response("search_spreadsheets", "Google account not connected or credentials are invalid.")

        try:
            escaped_query = self._escape_drive_query(query)
            drive_query = (
                f"mimeType='{self._SPREADSHEET_MIME}' and trashed=false and "
                f"(name contains '{escaped_query}' or fullText contains '{escaped_query}')"
            )
            results = service.files().list(
                q=drive_query,
                pageSize=max_results,
                fields="files(id,name,webViewLink,modifiedTime,owners(displayName,emailAddress))",
                orderBy="modifiedTime desc",
            ).execute()
            files = results.get("files", []) or []

            items = [
                {
                    "id": file.get("id"),
                    "name": file.get("name"),
                    "url": file.get("webViewLink"),
                    "modified_time": file.get("modifiedTime"),
                    "owner": ((file.get("owners") or [{}])[0]).get("displayName"),
                }
                for file in files
            ]

            summary = f"Found {len(items)} spreadsheet(s) for '{query}'."
            metadata = self._build_metadata(
                action="search_spreadsheets",
                preview_type="sheet_list",
                title="Spreadsheet search results",
                summary=summary,
                inline={"items": items[:10], "count": len(items), "query": query},
            )
            return self._respond(True, summary, data={"query": query, "items": items}, metadata=metadata)
        except HttpError as error:
            return self._error_response("search_spreadsheets", self._http_error_message(error))

    def get_spreadsheet_info(self, spreadsheet_id_or_url: str) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("get_spreadsheet_info", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        if not spreadsheet_id:
            return self._error_response("get_spreadsheet_info", "Please provide a valid spreadsheet ID or URL.")

        try:
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields=(
                    "spreadsheetId,spreadsheetUrl,properties(title,locale,timeZone),"
                    "sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount,frozenRowCount,frozenColumnCount)))"
                ),
            ).execute()

            sheets = spreadsheet.get("sheets", []) or []
            sheet_info = []
            for sheet in sheets:
                props = sheet.get("properties", {}) or {}
                grid = props.get("gridProperties", {}) or {}
                sheet_info.append(
                    {
                        "sheet_id": props.get("sheetId"),
                        "title": props.get("title"),
                        "index": props.get("index"),
                        "row_count": grid.get("rowCount"),
                        "column_count": grid.get("columnCount"),
                        "frozen_rows": grid.get("frozenRowCount"),
                        "frozen_columns": grid.get("frozenColumnCount"),
                    }
                )

            title = ((spreadsheet.get("properties") or {}).get("title")) or "Untitled spreadsheet"
            summary = f"Loaded spreadsheet '{title}' with {len(sheet_info)} sheet(s)."
            metadata = self._build_metadata(
                action="get_spreadsheet_info",
                preview_type="sheet_info",
                title="Spreadsheet details",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=spreadsheet.get("spreadsheetUrl"),
                inline={
                    "title": title,
                    "locale": (spreadsheet.get("properties") or {}).get("locale"),
                    "time_zone": (spreadsheet.get("properties") or {}).get("timeZone"),
                    "sheet_count": len(sheet_info),
                    "sheets": sheet_info[:15],
                },
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": spreadsheet.get("spreadsheetUrl"),
                    "title": title,
                    "locale": (spreadsheet.get("properties") or {}).get("locale"),
                    "time_zone": (spreadsheet.get("properties") or {}).get("timeZone"),
                    "sheets": sheet_info,
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "get_spreadsheet_info",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def list_sheet_titles(self, spreadsheet_id_or_url: str) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("list_sheet_titles", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        if not spreadsheet_id:
            return self._error_response("list_sheet_titles", "Please provide a valid spreadsheet ID or URL.")

        try:
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="spreadsheetId,spreadsheetUrl,sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount)))",
            ).execute()
            sheets = spreadsheet.get("sheets", []) or []
            items = []
            for sheet in sheets:
                props = sheet.get("properties", {}) or {}
                grid = props.get("gridProperties", {}) or {}
                items.append(
                    {
                        "sheet_id": props.get("sheetId"),
                        "title": props.get("title"),
                        "index": props.get("index"),
                        "row_count": grid.get("rowCount"),
                        "column_count": grid.get("columnCount"),
                    }
                )

            summary = f"Found {len(items)} sheet tab(s)."
            metadata = self._build_metadata(
                action="list_sheet_titles",
                preview_type="sheet_list",
                title="Sheet tabs",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=spreadsheet.get("spreadsheetUrl"),
                inline={"items": items, "count": len(items)},
            )
            return self._respond(
                True,
                summary,
                data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet.get("spreadsheetUrl"), "sheets": items},
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "list_sheet_titles",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def read_range(
        self,
        spreadsheet_id_or_url: str,
        range_name: str,
        value_render_option: str = "UNFORMATTED_VALUE",
        date_time_render_option: str = "FORMATTED_STRING",
    ) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("read_range", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        if not spreadsheet_id:
            return self._error_response("read_range", "Please provide a valid spreadsheet ID or URL.")
        if not str(range_name or "").strip():
            return self._error_response("read_range", "Please provide a valid A1 range (for example: Sheet1!A1:D50).")

        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueRenderOption=value_render_option,
                dateTimeRenderOption=date_time_render_option,
            ).execute()
            values = result.get("values", []) or []

            table_inline = self._build_table_inline(values, range_name=range_name)
            summary = f"Read {table_inline.get('row_count', 0)} row(s) from {range_name}."
            metadata = self._build_metadata(
                action="read_range",
                preview_type="sheet_table",
                title="Sheet range preview",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                range_name=range_name,
                inline=table_inline,
                operation="read",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "range": result.get("range", range_name),
                    "major_dimension": result.get("majorDimension", "ROWS"),
                    "values": values,
                    "row_count": table_inline.get("row_count", 0),
                    "column_count": table_inline.get("column_count", 0),
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "read_range",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def batch_read_ranges(self, spreadsheet_id_or_url: str, ranges_json: Any) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("batch_read_ranges", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        if not spreadsheet_id:
            return self._error_response("batch_read_ranges", "Please provide a valid spreadsheet ID or URL.")

        ranges = self._normalize_ranges(ranges_json)
        if not ranges:
            return self._error_response("batch_read_ranges", "Provide ranges as a JSON array or comma-separated string.")

        try:
            response = service.spreadsheets().values().batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=ranges,
                majorDimension="ROWS",
                valueRenderOption="UNFORMATTED_VALUE",
            ).execute()
            value_ranges = response.get("valueRanges", []) or []

            normalized_ranges = []
            for item in value_ranges:
                values = item.get("values", []) or []
                normalized_ranges.append(
                    {
                        "range": item.get("range"),
                        "values": values,
                        "row_count": len(values),
                        "column_count": max((len(row) for row in values), default=0),
                    }
                )

            first_values = normalized_ranges[0]["values"] if normalized_ranges else []
            first_range = normalized_ranges[0]["range"] if normalized_ranges else None
            table_inline = self._build_table_inline(first_values, range_name=first_range)
            summary = f"Read {len(normalized_ranges)} range(s) from spreadsheet."
            metadata = self._build_metadata(
                action="batch_read_ranges",
                preview_type="sheet_table",
                title="Batch range preview",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                inline={
                    **table_inline,
                    "batch_count": len(normalized_ranges),
                    "ranges": [item.get("range") for item in normalized_ranges],
                },
                operation="read",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "ranges": normalized_ranges,
                    "range_count": len(normalized_ranges),
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "batch_read_ranges",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def write_range(
        self,
        spreadsheet_id_or_url: str,
        range_name: str,
        values_json: Any,
        value_input_option: str = "USER_ENTERED",
    ) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("write_range", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        values = self._normalize_values(values_json)
        if not spreadsheet_id:
            return self._error_response("write_range", "Please provide a valid spreadsheet ID or URL.")
        if not str(range_name or "").strip():
            return self._error_response("write_range", "Please provide a target A1 range.")
        if not values:
            return self._error_response("write_range", "No values provided. Pass values as a JSON array.")

        try:
            response = service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body={"values": values},
            ).execute()

            table_inline = self._build_table_inline(values, range_name=range_name)
            summary = (
                f"Wrote {response.get('updatedRows', 0)} row(s) and {response.get('updatedCells', 0)} cell(s) "
                f"to {response.get('updatedRange', range_name)}."
            )
            metadata = self._build_metadata(
                action="write_range",
                preview_type="sheet_table",
                title="Written range preview",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                range_name=response.get("updatedRange", range_name),
                inline=table_inline,
                operation="write",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "updated_range": response.get("updatedRange", range_name),
                    "updated_rows": response.get("updatedRows", 0),
                    "updated_columns": response.get("updatedColumns", 0),
                    "updated_cells": response.get("updatedCells", 0),
                    "values_written": values,
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "write_range",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def append_rows(
        self,
        spreadsheet_id_or_url: str,
        range_name: str,
        values_json: Any,
        value_input_option: str = "USER_ENTERED",
        insert_data_option: str = "INSERT_ROWS",
    ) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("append_rows", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        values = self._normalize_values(values_json)
        if not spreadsheet_id:
            return self._error_response("append_rows", "Please provide a valid spreadsheet ID or URL.")
        if not str(range_name or "").strip():
            return self._error_response("append_rows", "Please provide an A1 range for append context.")
        if not values:
            return self._error_response("append_rows", "No values provided. Pass values as a JSON array.")

        try:
            response = service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                insertDataOption=insert_data_option,
                body={"values": values},
            ).execute()
            updates = (response.get("updates") or {}) if isinstance(response, dict) else {}

            updated_range = updates.get("updatedRange", range_name)
            summary = (
                f"Appended {updates.get('updatedRows', len(values))} row(s) "
                f"to {updated_range}."
            )
            metadata = self._build_metadata(
                action="append_rows",
                preview_type="sheet_table",
                title="Appended rows preview",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                range_name=updated_range,
                inline=self._build_table_inline(values, range_name=updated_range),
                operation="append",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "table_range": updates.get("tableRange"),
                    "updated_range": updated_range,
                    "updated_rows": updates.get("updatedRows", len(values)),
                    "updated_columns": updates.get("updatedColumns", 0),
                    "updated_cells": updates.get("updatedCells", 0),
                    "values_appended": values,
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "append_rows",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def batch_write_ranges(
        self,
        spreadsheet_id_or_url: str,
        updates_json: Any,
        value_input_option: str = "USER_ENTERED",
    ) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("batch_write_ranges", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        updates = self._normalize_batch_updates(updates_json)
        if not spreadsheet_id:
            return self._error_response("batch_write_ranges", "Please provide a valid spreadsheet ID or URL.")
        if not updates:
            return self._error_response(
                "batch_write_ranges",
                "No valid updates found. Provide JSON like [{\"range\":\"Sheet1!A1:B2\",\"values\":[[1,2],[3,4]]}].",
            )

        try:
            response = service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": value_input_option,
                    "data": updates,
                },
            ).execute()
            first_update = updates[0]
            summary = (
                f"Batch wrote {response.get('totalUpdatedCells', 0)} cell(s) "
                f"across {len(updates)} range(s)."
            )
            metadata = self._build_metadata(
                action="batch_write_ranges",
                preview_type="sheet_table",
                title="Batch write preview",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                range_name=first_update.get("range"),
                inline={
                    **self._build_table_inline(first_update.get("values", []), range_name=first_update.get("range")),
                    "batch_count": len(updates),
                    "ranges": [update.get("range") for update in updates],
                },
                operation="batch_write",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "total_updated_rows": response.get("totalUpdatedRows", 0),
                    "total_updated_columns": response.get("totalUpdatedColumns", 0),
                    "total_updated_cells": response.get("totalUpdatedCells", 0),
                    "total_updated_sheets": response.get("totalUpdatedSheets", 0),
                    "updates": updates,
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "batch_write_ranges",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def clear_range(self, spreadsheet_id_or_url: str, range_name: str) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("clear_range", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        if not spreadsheet_id:
            return self._error_response("clear_range", "Please provide a valid spreadsheet ID or URL.")
        if not str(range_name or "").strip():
            return self._error_response("clear_range", "Please provide the range to clear.")

        try:
            response = service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                body={},
            ).execute()
            cleared_range = response.get("clearedRange", range_name)
            summary = f"Cleared cells in range {cleared_range}."
            metadata = self._build_metadata(
                action="clear_range",
                preview_type="sheet_info",
                title="Range cleared",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                range_name=cleared_range,
                inline={"cleared_range": cleared_range},
                operation="clear",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "cleared_range": cleared_range,
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "clear_range",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def add_sheet(self, spreadsheet_id_or_url: str, sheet_title: str, rows: int = 1000, columns: int = 26) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("add_sheet", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        safe_title = str(sheet_title or "").strip()
        if not spreadsheet_id:
            return self._error_response("add_sheet", "Please provide a valid spreadsheet ID or URL.")
        if not safe_title:
            return self._error_response("add_sheet", "Please provide a non-empty sheet title.")

        try:
            body = {
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": safe_title,
                                "gridProperties": {
                                    "rowCount": max(1, int(rows)),
                                    "columnCount": max(1, int(columns)),
                                },
                            }
                        }
                    }
                ]
            }
            response = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
            replies = response.get("replies", []) or []
            add_sheet_reply = (replies[0].get("addSheet") if replies and isinstance(replies[0], dict) else {}) or {}
            properties = add_sheet_reply.get("properties", {}) or {}

            summary = f"Added sheet '{safe_title}'."
            metadata = self._build_metadata(
                action="add_sheet",
                preview_type="sheet_info",
                title="Sheet added",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                sheet_title=safe_title,
                inline={
                    "sheet_id": properties.get("sheetId"),
                    "sheet_title": properties.get("title", safe_title),
                    "rows": ((properties.get("gridProperties") or {}).get("rowCount")),
                    "columns": ((properties.get("gridProperties") or {}).get("columnCount")),
                },
                operation="add_sheet",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "sheet_id": properties.get("sheetId"),
                    "sheet_title": properties.get("title", safe_title),
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "add_sheet",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def rename_sheet(self, spreadsheet_id_or_url: str, current_title: str, new_title: str) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("rename_sheet", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        source_title = str(current_title or "").strip()
        target_title = str(new_title or "").strip()
        if not spreadsheet_id:
            return self._error_response("rename_sheet", "Please provide a valid spreadsheet ID or URL.")
        if not source_title or not target_title:
            return self._error_response("rename_sheet", "Provide both current_title and new_title.")

        try:
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title))",
            ).execute()
            sheet_map = self._get_sheet_map(spreadsheet)
            props = sheet_map.get(source_title)
            if not props:
                return self._error_response(
                    "rename_sheet",
                    f"Sheet '{source_title}' was not found.",
                    spreadsheet_id=spreadsheet_id,
                    spreadsheet_url=self._sheet_url(spreadsheet_id),
                )

            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "properties": {
                                    "sheetId": props.get("sheetId"),
                                    "title": target_title,
                                },
                                "fields": "title",
                            }
                        }
                    ]
                },
            ).execute()

            summary = f"Renamed sheet '{source_title}' to '{target_title}'."
            metadata = self._build_metadata(
                action="rename_sheet",
                preview_type="sheet_info",
                title="Sheet renamed",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                sheet_title=target_title,
                inline={
                    "sheet_id": props.get("sheetId"),
                    "previous_title": source_title,
                    "new_title": target_title,
                },
                operation="rename_sheet",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "sheet_id": props.get("sheetId"),
                    "previous_title": source_title,
                    "new_title": target_title,
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "rename_sheet",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def delete_sheet(self, spreadsheet_id_or_url: str, sheet_title: str) -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("delete_sheet", "Google account not connected or credentials are invalid.")

        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_id_or_url)
        target_title = str(sheet_title or "").strip()
        if not spreadsheet_id:
            return self._error_response("delete_sheet", "Please provide a valid spreadsheet ID or URL.")
        if not target_title:
            return self._error_response("delete_sheet", "Provide the sheet title to delete.")

        try:
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title))",
            ).execute()
            sheet_map = self._get_sheet_map(spreadsheet)
            props = sheet_map.get(target_title)
            if not props:
                return self._error_response(
                    "delete_sheet",
                    f"Sheet '{target_title}' was not found.",
                    spreadsheet_id=spreadsheet_id,
                    spreadsheet_url=self._sheet_url(spreadsheet_id),
                )

            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"deleteSheet": {"sheetId": props.get("sheetId")}}]},
            ).execute()

            summary = f"Deleted sheet '{target_title}'."
            metadata = self._build_metadata(
                action="delete_sheet",
                preview_type="sheet_info",
                title="Sheet deleted",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                inline={"sheet_id": props.get("sheetId"), "deleted_title": target_title},
                operation="delete_sheet",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": self._sheet_url(spreadsheet_id),
                    "sheet_id": props.get("sheetId"),
                    "deleted_title": target_title,
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response(
                "delete_sheet",
                self._http_error_message(error),
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=self._sheet_url(spreadsheet_id),
            )

    def create_spreadsheet(self, title: str, first_sheet_title: str = "Sheet1") -> str:
        service = self._get_sheets_service()
        if not service:
            return self._error_response("create_spreadsheet", "Google account not connected or credentials are invalid.")

        safe_title = str(title or "").strip()
        safe_sheet_title = str(first_sheet_title or "Sheet1").strip() or "Sheet1"
        if not safe_title:
            return self._error_response("create_spreadsheet", "Please provide a spreadsheet title.")

        try:
            spreadsheet = service.spreadsheets().create(
                body={
                    "properties": {"title": safe_title},
                    "sheets": [{"properties": {"title": safe_sheet_title}}],
                },
                fields="spreadsheetId,spreadsheetUrl,properties(title),sheets(properties(sheetId,title))",
            ).execute()
            spreadsheet_id = spreadsheet.get("spreadsheetId")
            spreadsheet_url = spreadsheet.get("spreadsheetUrl") or (self._sheet_url(spreadsheet_id) if spreadsheet_id else None)
            first_sheet = ((spreadsheet.get("sheets") or [{}])[0].get("properties") or {})

            summary = f"Created spreadsheet '{safe_title}'."
            metadata = self._build_metadata(
                action="create_spreadsheet",
                preview_type="sheet_info",
                title="Spreadsheet created",
                summary=summary,
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=spreadsheet_url,
                sheet_title=first_sheet.get("title", safe_sheet_title),
                inline={
                    "spreadsheet_title": safe_title,
                    "spreadsheet_id": spreadsheet_id,
                    "first_sheet_title": first_sheet.get("title", safe_sheet_title),
                },
                operation="create_spreadsheet",
            )
            return self._respond(
                True,
                summary,
                data={
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_url": spreadsheet_url,
                    "spreadsheet_title": safe_title,
                    "first_sheet_title": first_sheet.get("title", safe_sheet_title),
                    "first_sheet_id": first_sheet.get("sheetId"),
                },
                metadata=metadata,
            )
        except HttpError as error:
            return self._error_response("create_spreadsheet", self._http_error_message(error))
