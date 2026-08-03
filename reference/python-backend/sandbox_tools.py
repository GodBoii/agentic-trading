# python-backend/sandbox_tools.py (Complete, Updated Version with Persistence)

import os
import base64
import mimetypes
import posixpath
import shlex
import requests
import eventlet
from agno.tools import Toolkit
from typing import Optional, Set, Dict, Any, List
from pathlib import PurePosixPath
import logging
from deploy_platform import (
    activate_deployment,
    get_deployment_file_bytes,
    get_deployment_summary,
    get_site_summary,
    list_deployment_files,
    resolve_site_ref,
    upload_site_files,
    upsert_site_manifest,
)

logger = logging.getLogger(__name__)

class SandboxTools(Toolkit):
    """
    A state-aware toolkit for interacting with an isolated sandbox environment.
    It ensures one sandbox is created and reused per session.
    Now includes automatic persistence of execution history to Postgres + R2.
    """
    def __init__(
        self, 
        session_info: Dict[str, Any],
        persistence_service=None,
        user_id: str = None,
        session_id: str = None,
        message_id: str = None,
        socketio=None,
        sid: str = None,
        redis_client=None,
        delegation_id: str = None,
        delegated_agent: str = None,
    ):
        """
        Initializes the SandboxTools with session-specific information.
        Args:
            session_info (Dict[str, Any]): The dictionary for the current user session.
            persistence_service: SandboxPersistenceService instance (optional)
            user_id: User ID for persistence (optional)
            session_id: Session ID for persistence (optional)
            message_id: Message ID for linking to frontend (optional)
            socketio: Socket.IO instance for real-time events (optional)
            sid: Socket ID for emitting events (optional)
        """
        super().__init__(
            name="sandbox_tools",
            tools=[
                self.get_workspace_overview,
                self.search_code,
                self.read_file,
                self.create_file,
                self.append_file_chunk,
                self.create_and_write,
                self.write_file,
                self.edit_file,
                self.execute_in_sandbox,
                self.copy_deployed_project,
                self.redeploy_project
            ]
        )
        self.session_info = session_info or {}
        self.workspace_root = "/home/sandboxuser/workspace"
        self.sandbox_api_url = os.getenv("SANDBOX_API_URL")
        if not self.sandbox_api_url:
            raise ValueError("SANDBOX_API_URL environment variable is not set.")
        
        # Persistence dependencies
        self.persistence_service = persistence_service
        self.user_id = user_id
        self.session_id = session_id
        self.message_id = message_id
        self.socketio = socketio
        self.sid = sid
        self.redis_client = redis_client
        self.delegation_id = delegation_id
        self.delegated_agent = delegated_agent

    def _frontend_room(self) -> Optional[str]:
        if self.session_id:
            return f"conv:{self.session_id}"
        return self.sid

    def _attach_delegation_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.delegation_id:
            payload["delegation_id"] = self.delegation_id
        if self.delegated_agent:
            payload["delegated_agent"] = self.delegated_agent
        return payload

    def _normalize_workspace_path(self, path: str) -> str:
        """
        Normalize and validate that a path stays under the workspace root.
        Accepts relative paths by resolving them against self.workspace_root.
        """
        if path is None:
            raise ValueError("Path is required.")
        raw = str(path).strip().replace("\\", "/")
        if not raw:
            raise ValueError("Path cannot be empty.")

        candidate = raw if raw.startswith("/") else f"{self.workspace_root}/{raw.lstrip('/')}"
        normalized = posixpath.normpath(candidate).replace("\\", "/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        root = self.workspace_root.rstrip("/")
        if normalized != root and not normalized.startswith(root + "/"):
            raise ValueError(f"Path must be under {self.workspace_root}")
        if ".." in PurePosixPath(normalized).parts:
            raise ValueError("Invalid path traversal.")

        return normalized

    def _is_sandbox_alive(self, sandbox_id: str) -> bool:
        try:
            response = requests.get(
                f"{self.sandbox_api_url}/sessions/{sandbox_id}/files",
                params={"path": self.workspace_root},
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False

    def _execute_manager_command(self, sandbox_id: str, command: str, timeout: int = 310) -> Dict[str, Any]:
        response = requests.post(
            f"{self.sandbox_api_url}/sessions/{sandbox_id}/exec",
            json={"command": command},
            timeout=timeout
        )
        response.raise_for_status()
        data = response.json() or {}
        return {
            "stdout": data.get("stdout", ""),
            "stderr": data.get("stderr", ""),
            "exit_code": int(data.get("exit_code", 0))
        }

    def _read_file_bytes(self, sandbox_id: str, filepath: str) -> bytes:
        safe_path = self._normalize_workspace_path(filepath)
        response = requests.get(
            f"{self.sandbox_api_url}/sessions/{sandbox_id}/files/content",
            params={"filepath": safe_path},
            timeout=30
        )
        response.raise_for_status()
        payload = response.json() or {}
        encoded = payload.get("content", "")
        if not encoded:
            return b""
        return base64.b64decode(encoded)

    def _append_file_bytes(self, sandbox_id: str, filepath: str, chunk_bytes: bytes) -> None:
        """
        Append raw bytes directly in sandbox using Python, avoiding full-file read/replace.
        """
        safe_path = self._normalize_workspace_path(filepath)
        encoded = base64.b64encode(chunk_bytes).decode("ascii")
        py_code = (
            "import base64, pathlib; "
            f"p=pathlib.Path({safe_path!r}); "
            "p.parent.mkdir(parents=True, exist_ok=True); "
            f"p.open('ab').write(base64.b64decode({encoded!r}))"
        )
        cmd = f"python3 -c {shlex.quote(py_code)} || python -c {shlex.quote(py_code)}"
        result = self._execute_manager_command(sandbox_id, cmd, timeout=120)
        if int(result.get("exit_code", 1)) != 0:
            stderr = (result.get("stderr") or "").strip()
            raise RuntimeError(f"Append command failed for {safe_path}: {stderr or 'unknown error'}")

    def _workspace_file_suggestions(self, sandbox_id: str, max_items: int = 20) -> List[str]:
        """
        Return a small list of relative file paths currently visible in workspace.
        Useful in error messages when requested path is missing.
        """
        try:
            response = requests.get(
                f"{self.sandbox_api_url}/sessions/{sandbox_id}/files",
                params={"path": self.workspace_root},
                timeout=20,
            )
            response.raise_for_status()
            files = response.json().get("files", []) or []
            rel = []
            for item in files:
                abs_path = str(item.get("path", ""))
                if abs_path.startswith(self.workspace_root + "/"):
                    rel.append(abs_path[len(self.workspace_root) + 1 :])
                elif abs_path:
                    rel.append(abs_path)
            rel.sort()
            return rel[:max_items]
        except Exception:
            return []

    def _resolve_target_path(
        self,
        file_path: Optional[str] = None,
        path: Optional[str] = None,
        filename: Optional[str] = None,
        default_filename: Optional[str] = None,
    ) -> Optional[str]:
        for candidate in (file_path, path, filename):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return default_filename

    def _resolve_text_content(
        self,
        content: Optional[str] = None,
        text: Optional[str] = None,
        body: Optional[str] = None,
        content_base64: Optional[str] = None,
    ) -> Optional[str]:
        if content_base64:
            try:
                return base64.b64decode(content_base64.encode("utf-8")).decode("utf-8", errors="replace")
            except Exception:
                return None
        for candidate in (content, text, body):
            if candidate is None:
                continue
            if isinstance(candidate, str):
                return candidate
            return str(candidate)
        return None

    def _file_exists(self, sandbox_id: str, filepath: str) -> bool:
        try:
            self._read_file_bytes(sandbox_id, filepath)
            return True
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 404:
                return False
            raise

    def _persist_file_tool_activity(
        self,
        sandbox_id: str,
        safe_path: str,
        file_bytes: bytes,
        tool_name: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Persist file-tool mutations so they appear in session content history.
        This mirrors the execution/artifact model used by execute_in_sandbox.
        Never raises to avoid breaking core file operations.
        """
        if not (self.persistence_service and self.user_id and self.session_id):
            return
        try:
            command = f"[file_tool:{tool_name}] {safe_path}"
            execution_id = self.persistence_service.create_execution_record(
                user_id=self.user_id,
                session_id=self.session_id,
                sandbox_id=sandbox_id,
                command=command,
                message_id=self.message_id,
            )
            if not execution_id:
                return

            meta = {"tool": tool_name, "file_path": safe_path, "size_bytes": len(file_bytes)}
            if extra:
                meta.update(extra)

            stdout = (
                f"Tool: {tool_name}\n"
                f"File: {safe_path}\n"
                f"Bytes: {len(file_bytes)}\n"
                f"Metadata: {meta}"
            )
            self.persistence_service.persist_execution_output(
                execution_id=execution_id,
                stdout=stdout,
                stderr="",
                exit_code=0,
            )

            artifact_id = self.persistence_service.create_artifact(
                execution_id=execution_id,
                user_id=self.user_id,
                session_id=self.session_id,
                sandbox_id=sandbox_id,
                file_path=safe_path,
                file_content=file_bytes,
                message_id=self.message_id,
            )

            if artifact_id and self.socketio and self._frontend_room():
                payload = self._attach_delegation_metadata(
                    {
                        "id": self.message_id,
                        "execution_id": execution_id,
                        "artifacts": [
                            {
                                "artifact_id": artifact_id,
                                "file_path": safe_path,
                                "size_bytes": len(file_bytes),
                                "execution_id": execution_id,
                            }
                        ],
                    }
                )
                self.socketio.emit(
                    "sandbox-artifacts-created",
                    payload,
                    room=self._frontend_room(),
                )
        except Exception as exc:
            logger.warning("Non-blocking file-tool persistence failed for %s: %s", safe_path, exc)

    def create_file(
        self,
        file_path: str,
        overwrite: bool = False,
        initial_content: Optional[str] = None,
        content: Optional[str] = None,
        text: Optional[str] = None,
        body: Optional[str] = None,
        content_base64: Optional[str] = None,
        path: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Create a file in workspace (optionally overwrite existing).
        Use this before edit_file for brand new files.
        """
        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."
        try:
            resolved = self._resolve_target_path(file_path=file_path, path=path, filename=filename)
            if not resolved:
                return "Error: file_path is required. Example: create_file(file_path='index.html')."

            safe_path = self._normalize_workspace_path(resolved)
            exists = self._file_exists(sandbox_id, safe_path)
            if exists and not overwrite:
                return f"Error: File already exists: {safe_path}. Set overwrite=True to replace it."

            resolved_initial_content = self._resolve_text_content(
                content=content if content is not None else initial_content,
                text=text,
                body=body,
                content_base64=content_base64,
            )
            if resolved_initial_content is None:
                resolved_initial_content = ""

            self._write_file_to_sandbox(
                sandbox_id=sandbox_id,
                filepath=safe_path,
                content_bytes=resolved_initial_content.encode("utf-8"),
            )
            self._persist_file_tool_activity(
                sandbox_id=sandbox_id,
                safe_path=safe_path,
                file_bytes=resolved_initial_content.encode("utf-8"),
                tool_name="create_file",
                extra={"overwrite": overwrite, "exists_before": exists},
            )
            action = "Overwritten" if exists else "Created"
            return f"{action} file: {safe_path}"
        except Exception as exc:
            logger.error("create_file failed: %s", exc, exc_info=True)
            return f"Error creating file: {exc}"

    def append_file_chunk(
        self,
        file_path: str,
        chunk: str,
        content: Optional[str] = None,
        text: Optional[str] = None,
        body: Optional[str] = None,
        chunk_base64: Optional[str] = None,
        create_if_missing: bool = True,
        path: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Append a small chunk to a file.
        Preferred for large generated files to avoid single-call JSON payload failures.
        """
        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."
        try:
            resolved = self._resolve_target_path(file_path=file_path, path=path, filename=filename)
            if not resolved:
                return "Error: file_path is required."
            safe_path = self._normalize_workspace_path(resolved)

            resolved_chunk = self._resolve_text_content(
                content=chunk if chunk is not None else content,
                text=text,
                body=body,
                content_base64=chunk_base64,
            )
            if resolved_chunk is None:
                return (
                    "Error: Missing chunk content. Provide chunk/text/body or chunk_base64."
                )

            chunk_bytes = resolved_chunk.encode("utf-8")
            exists = self._file_exists(sandbox_id, safe_path)
            if not exists and not create_if_missing:
                return f"Error: File not found: {safe_path}"

            self._append_file_bytes(sandbox_id=sandbox_id, filepath=safe_path, chunk_bytes=chunk_bytes)
            final_bytes = self._read_file_bytes(sandbox_id, safe_path)
            self._persist_file_tool_activity(
                sandbox_id=sandbox_id,
                safe_path=safe_path,
                file_bytes=final_bytes,
                tool_name="append_file_chunk",
                extra={"appended_bytes": len(chunk_bytes), "create_if_missing": create_if_missing},
            )
            return f"Appended {len(chunk_bytes)} bytes to {safe_path}."
        except Exception as exc:
            logger.error("append_file_chunk failed: %s", exc, exc_info=True)
            return f"Error appending file chunk: {exc}"

    def create_and_write(
        self,
        file_path: str,
        content: str,
        text: Optional[str] = None,
        body: Optional[str] = None,
        content_base64: Optional[str] = None,
        overwrite: bool = True,
        path: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Create (or overwrite) a file and write full content in one call.
        Best for small/medium payloads; for large payloads prefer create_file + append_file_chunk.
        """
        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."
        try:
            resolved = self._resolve_target_path(
                file_path=file_path,
                path=path,
                filename=filename,
            )
            if not resolved:
                return "Error: file_path is required."
            safe_path = self._normalize_workspace_path(resolved)

            resolved_content = self._resolve_text_content(
                content=content,
                text=text,
                body=body,
                content_base64=content_base64,
            )
            if resolved_content is None:
                return (
                    "Error: Missing file content. Provide content/text/body or content_base64."
                )

            exists = self._file_exists(sandbox_id, safe_path)
            if exists and not overwrite:
                return f"Error: File already exists: {safe_path}. Set overwrite=True to replace it."

            payload = resolved_content.encode("utf-8")
            self._write_file_to_sandbox(
                sandbox_id=sandbox_id,
                filepath=safe_path,
                content_bytes=payload,
            )
            self._persist_file_tool_activity(
                sandbox_id=sandbox_id,
                safe_path=safe_path,
                file_bytes=payload,
                tool_name="create_and_write",
                extra={"overwrite": overwrite, "exists_before": exists},
            )

            # Soft warning for reliability when very large content is pushed in one call.
            if len(payload) > 40_000:
                return (
                    f"Wrote {len(payload)} bytes to {safe_path}. "
                    "For higher reliability on very large files, prefer create_file + append_file_chunk in small chunks."
                )
            return f"Wrote {len(payload)} bytes to {safe_path}."
        except Exception as exc:
            logger.error("create_and_write failed: %s", exc, exc_info=True)
            return f"Error creating and writing file: {exc}"

    def _create_or_get_sandbox_id(self) -> Optional[str]:
        """
        Internal helper function. Creates a new sandbox if one doesn't exist for this session,
        otherwise returns the ID of the existing sandbox.
        Returns the unique sandbox_id string or None if creation fails.
        """
        active_id = self.session_info.get("active_sandbox_id")
        if active_id and self._is_sandbox_alive(active_id):
            return active_id
        if active_id:
            self.session_info.pop("active_sandbox_id", None)

        # Reuse the newest known sandbox from session state before creating a new one.
        known_ids = list(self.session_info.get("sandbox_ids", []))
        for known_id in reversed(known_ids):
            if known_id and self._is_sandbox_alive(known_id):
                self.session_info["active_sandbox_id"] = known_id
                return known_id

        try:
            response = requests.post(f"{self.sandbox_api_url}/sessions", timeout=30)
            response.raise_for_status()
            data = response.json()
            new_sandbox_id = data.get("sandbox_id")

            if new_sandbox_id:
                self.session_info["active_sandbox_id"] = new_sandbox_id
                # This correctly handles the list from Redis session data.
                if "sandbox_ids" not in self.session_info:
                    self.session_info["sandbox_ids"] = []
                if new_sandbox_id not in self.session_info["sandbox_ids"]:
                    self.session_info["sandbox_ids"].append(new_sandbox_id)
                
                # Persist to Redis so the manager can terminate it later
                if getattr(self, "redis_client", None) and getattr(self, "session_id", None):
                    try:
                        from session_service import ConnectionManager
                        cm = ConnectionManager(self.redis_client)
                        cm.add_sandbox_to_session(self.session_id, new_sandbox_id)
                        logger.info(f"Persisted sandbox_id {new_sandbox_id} to Redis for session {self.session_id}")
                    except Exception as e:
                        logger.error(f"Failed to persist sandbox_id to Redis: {e}", exc_info=True)
                
                return new_sandbox_id
            else:
                logger.error("Sandbox: No valid ID returned")
                return None

        except requests.RequestException as e:
            logger.error(f"Sandbox creation failed: {e}")
            return None

    def get_workspace_overview(self, max_files: int = 200) -> str:
        """
        Return a concise workspace file listing for planning and navigation.
        """
        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."
        try:
            max_files = max(1, min(int(max_files), 1000))
            response = requests.get(
                f"{self.sandbox_api_url}/sessions/{sandbox_id}/files",
                params={"path": self.workspace_root},
                timeout=30
            )
            response.raise_for_status()
            files = response.json().get("files", []) or []
            files = sorted(files, key=lambda f: str(f.get("path", "")))
            total = len(files)
            shown = files[:max_files]
            lines = [
                f"Sandbox: {sandbox_id}",
                f"Workspace root: {self.workspace_root}",
                f"Total files: {total}",
                f"Showing: {len(shown)}",
            ]
            for item in shown:
                abs_path = str(item.get("path", ""))
                rel = abs_path[len(self.workspace_root) + 1:] if abs_path.startswith(self.workspace_root + "/") else abs_path
                lines.append(f"- {rel} ({int(item.get('size', 0))} bytes)")
            if total > max_files:
                lines.append(f"... {total - max_files} more files not shown")
            return "\n".join(lines)
        except Exception as exc:
            logger.error("get_workspace_overview failed: %s", exc, exc_info=True)
            return f"Error reading workspace overview: {exc}"

    def search_code(
        self,
        query: str,
        path: str = "/home/sandboxuser/workspace",
        file_glob: Optional[str] = None,
        case_sensitive: bool = False,
        max_results: int = 100
    ) -> str:
        """
        Search code in workspace using rg (fallback to grep). Returns file:line:content results.
        """
        if not str(query).strip():
            return "Error: query cannot be empty."

        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."

        try:
            safe_path = self._normalize_workspace_path(path)
            max_results = max(1, min(int(max_results), 500))
            query_q = shlex.quote(str(query))
            path_q = shlex.quote(safe_path)
            head_q = shlex.quote(str(max_results))
            glob_clause = f"--glob {shlex.quote(str(file_glob))} " if file_glob else ""
            case_flag = "" if case_sensitive else "-i "

            command = (
                "if command -v rg >/dev/null 2>&1; then "
                f"rg --line-number --no-heading --color never {case_flag}{glob_clause}-- {query_q} {path_q}; "
                "else "
                f"grep -RIn --binary-files=without-match {'' if case_sensitive else '-i '}-- {query_q} {path_q}; "
                "fi | head -n " + head_q
            )

            result = self._execute_manager_command(sandbox_id, command, timeout=120)
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = int(result.get("exit_code", 0))

            if exit_code not in (0, 1):
                return f"Error searching code (exit {exit_code}): {stderr or stdout}"
            if not stdout.strip():
                return "No matches found."

            return stdout.strip()
        except Exception as exc:
            logger.error("search_code failed: %s", exc, exc_info=True)
            return f"Error searching code: {exc}"

    def read_file(
        self,
        file_path: str,
        start_line: int = 1,
        end_line: int = 200,
        path: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Read a workspace file with optional line range and line numbers.
        """
        resolved_path = file_path or path or filename
        if not resolved_path:
            return (
                "Error: Missing file path. Provide file_path (or path/filename in your tool call). "
                "Example: read_file(file_path='index.html', start_line=1, end_line=200)"
            )
        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."
        try:
            safe_path = self._normalize_workspace_path(resolved_path)
            start_line = max(1, int(start_line))
            end_line = max(start_line, int(end_line))
            if end_line - start_line > 2000:
                end_line = start_line + 2000

            try:
                data = self._read_file_bytes(sandbox_id, safe_path)
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 404:
                    suggestions = self._workspace_file_suggestions(sandbox_id)
                    hint = (
                        "\nWorkspace files (sample):\n- " + "\n- ".join(suggestions)
                        if suggestions else ""
                    )
                    return f"Error: File not found: {safe_path}{hint}"
                raise
            if not data:
                return f"{safe_path} is empty."
            if b"\x00" in data:
                return f"Error: {safe_path} appears to be a binary file."

            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()
            total = len(lines)
            slice_lines = lines[start_line - 1:end_line]
            numbered = [f"{idx}: {content}" for idx, content in enumerate(slice_lines, start=start_line)]

            header = f"File: {safe_path} (lines {start_line}-{min(end_line, total)} of {total})"
            body = "\n".join(numbered) if numbered else "(No lines in requested range)"
            return f"{header}\n{body}"
        except Exception as exc:
            logger.error("read_file failed: %s", exc, exc_info=True)
            return f"Error reading file: {exc}"

    # FUNCTION DESCRIPTION:
    # Writes UTF-8 text or Base64 binary bytes to a file inside the sandboxed workspace.
    # It routes paths through safe workspace normalizations, invokes the sandbox manager REST API,
    # and registers the file modification history.
    #
    # UPSTREAM CALLERS:
    # - Called directly by Agno agents (e.g. Coder agent) during code generation tasks.
    # - Called by workspace bootstrappers like `_ensure_project_workspace_bootstrap()`.
    #
    # DOWNSTREAM IMPACT:
    # - Modifies container storage in the Docker sandbox instance.
    # - Triggers `_persist_file_tool_activity()` which saves the modification details to Supabase
    #   'session_content' history tables, allowing downstream runners to build historical context maps.
    def write_file(
        self,
        file_path: str,
        content: str,
        text: Optional[str] = None,
        body: Optional[str] = None,
        content_base64: Optional[str] = None,
        append: bool = False,
        path: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Write UTF-8 text to a workspace file.
        Flexible inputs:
        - path can be passed as file_path/path/filename
        - content can be passed as content/text/body/content_base64
        - append=True appends to existing file (creates file if missing)
        """
        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."
        try:
            resolved_path = self._resolve_target_path(
                file_path=file_path,
                path=path,
                filename=filename,
            )
            resolved_content = self._resolve_text_content(
                content=content,
                text=text,
                body=body,
                content_base64=content_base64,
            )

            if resolved_content is None:
                return (
                    "Error: Missing file content. Provide content (or text/body/content_base64). "
                    "Example: write_file(file_path='index.html', content='<!doctype html>...')"
                )

            safe_path = self._normalize_workspace_path(resolved_path)
            payload_bytes = resolved_content.encode("utf-8")

            if append:
                self._append_file_bytes(sandbox_id=sandbox_id, filepath=safe_path, chunk_bytes=payload_bytes)
                final_bytes = self._read_file_bytes(sandbox_id, safe_path)
                self._persist_file_tool_activity(
                    sandbox_id=sandbox_id,
                    safe_path=safe_path,
                    file_bytes=final_bytes,
                    tool_name="write_file",
                    extra={"append": True, "appended_bytes": len(payload_bytes)},
                )
                return f"Appended {len(payload_bytes)} bytes to {safe_path}."

            self._write_file_to_sandbox(sandbox_id=sandbox_id, filepath=safe_path, content_bytes=payload_bytes)
            self._persist_file_tool_activity(
                sandbox_id=sandbox_id,
                safe_path=safe_path,
                file_bytes=payload_bytes,
                tool_name="write_file",
                extra={"append": False},
            )
            if len(payload_bytes) > 40_000:
                return (
                    f"Wrote {len(payload_bytes)} bytes to {safe_path}. "
                    "For higher reliability on very large files, prefer create_file + append_file_chunk with small chunks."
                )
            return f"Wrote {len(payload_bytes)} bytes to {safe_path}."
        except Exception as exc:
            logger.error("write_file failed: %s", exc, exc_info=True)
            return f"Error writing file: {exc}"

    def edit_file(
        self,
        file_path: str,
        search_text: str,
        replace_text: str,
        replace_all: bool = False,
        path: Optional[str] = None,
        find_text: Optional[str] = None,
        replacement: Optional[str] = None,
        create_if_missing: bool = False,
    ) -> str:
        """
        Perform deterministic text replacement on a workspace file.
        - If multiple matches exist and replace_all is False, returns an error for precision.
        """
        resolved_path = file_path or path
        resolved_search = search_text if search_text is not None else find_text
        resolved_replace = replace_text if replace_text is not None else replacement
        if not resolved_path:
            return "Error: file_path is required."
        if not resolved_search:
            return "Error: search_text cannot be empty."
        if resolved_replace is None:
            return "Error: replace_text is required."

        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."
        try:
            safe_path = self._normalize_workspace_path(resolved_path)
            try:
                raw = self._read_file_bytes(sandbox_id, safe_path)
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 404:
                    if create_if_missing:
                        created = str(resolved_replace)
                        self._write_file_to_sandbox(
                            sandbox_id=sandbox_id,
                            filepath=safe_path,
                            content_bytes=created.encode("utf-8"),
                        )
                        return f"Created missing file {safe_path} with provided replacement content."
                    suggestions = self._workspace_file_suggestions(sandbox_id)
                    hint = (
                        "\nWorkspace files (sample):\n- " + "\n- ".join(suggestions)
                        if suggestions else ""
                    )
                    return (
                        f"Error: File not found: {safe_path}. "
                        "Use get_workspace_overview/read_file to confirm path, or set create_if_missing=True."
                        f"{hint}"
                    )
                raise
            if b"\x00" in raw:
                return f"Error: {safe_path} appears to be a binary file."

            original = raw.decode("utf-8", errors="replace")
            hits = original.count(resolved_search)
            if hits == 0:
                return "Error: search_text was not found in file."
            if hits > 1 and not replace_all:
                return (
                    f"Error: search_text matched {hits} times. "
                    "Refine search_text or set replace_all=True."
                )

            updated = (
                original.replace(resolved_search, resolved_replace)
                if replace_all
                else original.replace(resolved_search, resolved_replace, 1)
            )
            self._write_file_to_sandbox(sandbox_id=sandbox_id, filepath=safe_path, content_bytes=updated.encode("utf-8"))
            self._persist_file_tool_activity(
                sandbox_id=sandbox_id,
                safe_path=safe_path,
                file_bytes=updated.encode("utf-8"),
                tool_name="edit_file",
                extra={"replace_all": replace_all, "matches": hits},
            )

            return (
                f"Updated {safe_path}. "
                f"Replacements applied: {hits if replace_all else 1}."
            )
        except Exception as exc:
            logger.error("edit_file failed: %s", exc, exc_info=True)
            return f"Error editing file: {exc}"

    # FUNCTION DESCRIPTION:
    # Executes a shell command inside the container using the Sandbox Manager API.
    # It logs starting states, saves execution details, gathers exit codes / streams,
    # and schedules async artifact scanners.
    #
    # UPSTREAM CALLERS:
    # - Called directly by Coder and Computer Agno agents during system tasks.
    #
    # DOWNSTREAM IMPACT:
    # - Spawns command processes inside the Docker container.
    # - Updates the execution database table 'sandbox_executions' via `persistence_service`.
    # - Emits WebSocket signals to the client (`sandbox-command-started`, `sandbox-command-finished`)
    #   which trigger CLI status displays in `js/chat.js`.
    # - Spawns `_detect_and_emit_artifacts_async()` to sweep filesystem updates, push new files to
    #   Supabase storage, and trigger visual panels in `js/artifact-handler.js`.
    def execute_in_sandbox(self, command: str) -> str:
        """
        Executes a shell command inside an isolated sandbox environment.
        If a sandbox for the current session does not exist, it will be created automatically.
        Now automatically persists execution history to Postgres + R2.
        Also tracks file artifacts created during execution.
        
        Args:
            command (str): The shell command to execute (e.g., 'ls -la', 'git clone ...').
        """
        # Get or create sandbox
        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve the sandbox session. Cannot execute command."
        
        # Snapshot files BEFORE execution (for artifact detection)
        files_before = set()
        if self.persistence_service and self.user_id and self.session_id:
            try:
                files_before = self._get_sandbox_files(sandbox_id)
            except Exception as e:
                logger.warning(f"Failed to snapshot files before execution: {e}")
        
        # Create execution record in Postgres (if persistence is enabled)
        execution_id = None
        if self.persistence_service and self.user_id and self.session_id:
            try:
                execution_id = self.persistence_service.create_execution_record(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    sandbox_id=sandbox_id,
                    command=command,
                    message_id=self.message_id
                )
                logger.info(f"Created execution record: {execution_id}")
                
                # Emit socket event: command started
                if self.socketio and self._frontend_room():
                    payload = self._attach_delegation_metadata({
                        "id": self.message_id,
                        "execution_id": execution_id,
                        "command": command
                    })
                    self.socketio.emit("sandbox-command-started", payload, room=self._frontend_room())
                    
            except Exception as e:
                logger.error(f"Failed to create execution record: {e}")
                # Don't fail the command execution if persistence fails
        
        # Execute command in sandbox
        try:
            data = self._execute_manager_command(sandbox_id=sandbox_id, command=command, timeout=310)
            
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            exit_code = data.get("exit_code", 0)
            
            # Persist output asynchronously (non-blocking)
            if execution_id and self.persistence_service:
                eventlet.spawn(
                    self._persist_output_async,
                    execution_id,
                    stdout,
                    stderr,
                    exit_code
                )
            
            # Emit socket event: command finished (without artifacts - they come later)
            if self.socketio and self._frontend_room():
                payload = self._attach_delegation_metadata({
                    "id": self.message_id,
                    "execution_id": execution_id,
                    "command": command,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code
                })
                self.socketio.emit("sandbox-command-finished", payload, room=self._frontend_room())
            
            # Detect and process artifacts AFTER emitting command finished
            # This happens asynchronously so chat isn't blocked
            if self.persistence_service and self.user_id and self.session_id and execution_id:
                eventlet.spawn(
                    self._detect_and_emit_artifacts_async,
                    sandbox_id,
                    execution_id,
                    files_before
                )
            
            # Format output for agent
            output = ""
            if stdout:
                output += f"STDOUT:\n{stdout}\n"
            if stderr:
                output += f"STDERR:\n{stderr}\n"
            if exit_code != 0:
                output += f"Exit Code: {exit_code}"

            return output if output else "Command executed successfully with no output."
            
        except requests.RequestException as e:
            logger.error(f"Failed to execute command in sandbox {sandbox_id}: {e}", exc_info=True)
            
            # Mark execution as failed if persistence is enabled
            if execution_id and self.persistence_service:
                try:
                    self.persistence_service.persist_execution_output(
                        execution_id=execution_id,
                        stdout="",
                        stderr=f"Error: {str(e)}",
                        exit_code=-1
                    )
                except:
                    pass
            
            return f"Error executing command: {e}"

    def copy_deployed_project(
        self,
        site_id: Optional[str] = None,
        deployment_id: Optional[str] = None,
        target_directory: str = "/home/sandboxuser/workspace/deployed_projects/current",
        site_ref: Optional[str] = None,
    ) -> str:
        """
        Copy files from an existing deployed project into the current sandbox.
        This avoids token-heavy file transfer through the model by doing backend-to-sandbox transfer directly.
        """
        if not self.user_id:
            return "Error: Missing user context for deployment access."

        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."

        try:
            resolved = resolve_site_ref(user_id=str(self.user_id), site_ref=(site_id or site_ref or "default"))
            resolved_site_id = str(resolved["id"])
            site = get_site_summary(site_id=resolved_site_id, user_id=str(self.user_id))
            deployment = get_deployment_summary(
                site_id=resolved_site_id,
                user_id=str(self.user_id),
                deployment_id=str(deployment_id) if deployment_id else None,
            )
            files = list_deployment_files(
                site_id=resolved_site_id,
                user_id=str(self.user_id),
                deployment_id=deployment["id"],
            )
            if not files:
                return "Error: Deployment has no files to copy."

            target_directory = str(target_directory).strip().rstrip("/") or f"{self.workspace_root}/deployed_projects/current"
            target_directory = self._normalize_workspace_path(target_directory)

            copied = 0
            for item in files:
                rel_path = str(item["path"]).replace("\\", "/").lstrip("/")
                if not rel_path or ".." in rel_path.split("/"):
                    continue
                content_bytes = get_deployment_file_bytes(
                    site_id=resolved_site_id,
                    user_id=str(self.user_id),
                    path=rel_path,
                    deployment_id=deployment["id"],
                )
                dest_path = f"{target_directory}/{rel_path}"
                self._write_file_to_sandbox(sandbox_id=sandbox_id, filepath=dest_path, content_bytes=content_bytes)
                copied += 1

            return (
                f"Copied {copied} file(s) from deployment {deployment['id']} for site {site['slug']} "
                f"into {target_directory} in sandbox {sandbox_id}."
            )
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.error("copy_deployed_project failed: %s", exc, exc_info=True)
            return f"Error copying deployed project: {exc}"

    def redeploy_project(
        self,
        site_id: Optional[str] = None,
        project_directory: str = "/home/sandboxuser/workspace/deployed_projects/current",
        activate: bool = True,
        site_ref: Optional[str] = None,
    ) -> str:
        """
        Redeploy a project from files in sandbox directory.
        The tool reads files from sandbox, uploads to hosting, and optionally activates deployment.
        """
        if not self.user_id:
            return "Error: Missing user context for deployment access."

        sandbox_id = self._create_or_get_sandbox_id()
        if not sandbox_id:
            return "Error: Failed to create or retrieve sandbox session."

        project_directory = self._normalize_workspace_path(str(project_directory).strip().rstrip("/"))

        try:
            resolved = resolve_site_ref(user_id=str(self.user_id), site_ref=(site_id or site_ref or "default"))
            resolved_site_id = str(resolved["id"])
            site = get_site_summary(site_id=resolved_site_id, user_id=str(self.user_id))

            list_resp = requests.get(
                f"{self.sandbox_api_url}/sessions/{sandbox_id}/files",
                params={"path": project_directory},
                timeout=60,
            )
            list_resp.raise_for_status()
            all_files = list_resp.json().get("files", []) or []
            if not all_files:
                return "Error: No files found in project_directory."

            upload_files: List[Dict[str, Any]] = []
            for item in all_files:
                abs_path = str(item.get("path", ""))
                if not abs_path.startswith(project_directory + "/"):
                    continue
                rel_path = abs_path[len(project_directory) + 1 :].replace("\\", "/")
                if not rel_path or ".." in rel_path.split("/"):
                    continue

                content_resp = requests.get(
                    f"{self.sandbox_api_url}/sessions/{sandbox_id}/files/content",
                    params={"filepath": abs_path},
                    timeout=60,
                )
                content_resp.raise_for_status()
                payload = content_resp.json() or {}
                content_b64 = payload.get("content", "")
                content_type = mimetypes.guess_type(rel_path)[0] or "application/octet-stream"
                upload_files.append(
                    {
                        "path": rel_path,
                        "content_base64": content_b64,
                        "content_type": content_type,
                    }
                )

            if not upload_files:
                return "Error: No deployable files found in project_directory."

            has_index = any(str(f.get("path", "")).lower() == "index.html" for f in upload_files)
            if not has_index:
                return "Error: Deployment must include index.html."

            upload = upload_site_files(site_id=resolved_site_id, user_id=str(self.user_id), files=upload_files)
            if not activate:
                return (
                    f"Uploaded {upload.files_uploaded} file(s) for site {site['slug']} as deployment "
                    f"{upload.deployment_id} (not activated)."
                )

            upsert_site_manifest(
                site_id=resolved_site_id,
                user_id=str(self.user_id),
                deployment_id=str(upload.deployment_id),
            )
            activated = activate_deployment(
                site_id=resolved_site_id,
                user_id=str(self.user_id),
                deployment_id=str(upload.deployment_id),
            )
            return (
                f"Redeployed site {site['slug']} successfully. "
                f"Deployment: {upload.deployment_id}, Files: {upload.files_uploaded}, URL: {activated.get('url')}"
            )
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.error("redeploy_project failed: %s", exc, exc_info=True)
            return f"Error redeploying project: {exc}"

    def _write_file_to_sandbox(self, sandbox_id: str, filepath: str, content_bytes: bytes) -> None:
        filepath = self._normalize_workspace_path(filepath)
        payload = {
            "filepath": filepath,
            "content_base64": base64.b64encode(content_bytes).decode("utf-8"),
            "make_dirs": True,
        }
        try:
            resp = requests.put(
                f"{self.sandbox_api_url}/sessions/{sandbox_id}/files/content",
                json=payload,
                timeout=60,
            )
            if resp.status_code == 405:
                self._write_file_to_sandbox_fallback(sandbox_id=sandbox_id, filepath=filepath, content_bytes=content_bytes)
                return
            resp.raise_for_status()
            return
        except requests.HTTPError:
            raise
        except Exception:
            # Network/proxy incompatibility fallback path.
            self._write_file_to_sandbox_fallback(sandbox_id=sandbox_id, filepath=filepath, content_bytes=content_bytes)

    def _write_file_to_sandbox_fallback(self, sandbox_id: str, filepath: str, content_bytes: bytes) -> None:
        """
        Fallback for environments where sandbox-manager PUT /files/content is unavailable.
        Writes file via sandbox exec + Python.
        """
        filepath = self._normalize_workspace_path(filepath)
        b64 = base64.b64encode(content_bytes).decode("utf-8")
        if len(b64) > 1_500_000:
            raise RuntimeError(
                "Sandbox file-write fallback hit payload limit. Restart sandbox-manager with updated PUT /files/content endpoint."
            )
        command = (
            "python3 - <<'PY'\n"
            "import base64, pathlib\n"
            f"p = pathlib.Path(r'''{filepath}''')\n"
            "p.parent.mkdir(parents=True, exist_ok=True)\n"
            f"p.write_bytes(base64.b64decode('''{b64}'''))\n"
            "print('ok')\n"
            "PY"
        )
        exec_resp = requests.post(
            f"{self.sandbox_api_url}/sessions/{sandbox_id}/exec",
            json={"command": command},
            timeout=120,
        )
        exec_resp.raise_for_status()
        result = exec_resp.json() or {}
        if int(result.get("exit_code", 1)) != 0:
            stderr = result.get("stderr", "")
            raise RuntimeError(f"Fallback file write failed: {stderr}")
    
    def _get_sandbox_files(self, sandbox_id: str) -> Set[str]:
        """
        Get set of file paths in sandbox.
        Used for detecting new files after command execution.
        
        Returns:
            Set of file paths
        """
        try:
            response = requests.get(
                f"{self.sandbox_api_url}/sessions/{sandbox_id}/files",
                params={"path": self.workspace_root},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Return set of file paths
            return {f['path'] for f in data.get('files', [])}
            
        except Exception as e:
            logger.error(f"Failed to list sandbox files: {e}")
            return set()
    
    def _process_artifacts(
        self,
        sandbox_id: str,
        execution_id: str,
        file_paths: Set[str],
        message_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Process new files as artifacts: download from sandbox, upload to R2, store in DB.
        
        Args:
            sandbox_id: Sandbox ID
            execution_id: Execution ID
            file_paths: Set of file paths to process
            message_id: Frontend message ID for linking
            
        Returns:
            List of artifact metadata dicts
        """
        artifacts = []
        
        # Limit to reasonable number of files
        MAX_ARTIFACTS = 20
        file_list = list(file_paths)[:MAX_ARTIFACTS]
        
        for file_path in file_list:
            try:
                # Skip system files and hidden files
                if file_path.startswith(f"{self.workspace_root}/."):
                    continue
                
                # Get file content from sandbox
                response = requests.get(
                    f"{self.sandbox_api_url}/sessions/{sandbox_id}/files/content",
                    params={"filepath": file_path},
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.warning(f"Failed to read file {file_path}: {response.status_code}")
                    continue
                
                file_data = response.json()
                file_content_raw = file_data.get('content', '')
                encoding = file_data.get('encoding', 'utf-8')
                
                # Decode based on encoding
                if encoding == 'base64':
                    import base64
                    file_content = base64.b64decode(file_content_raw)
                elif isinstance(file_content_raw, str):
                    file_content = file_content_raw.encode('utf-8')
                elif isinstance(file_content_raw, bytes):
                    file_content = file_content_raw
                else:
                    # It's likely a list of integers (byte array from JSON)
                    file_content = bytes(file_content_raw)
                
                # Skip empty files
                if not file_content or len(file_content) == 0:
                    continue
                
                # Skip very large files (> 10MB)
                if len(file_content) > 10 * 1024 * 1024:
                    logger.warning(f"Skipping large file {file_path}: {len(file_content)} bytes")
                    continue
                
                # Create artifact in persistence service
                artifact_id = self.persistence_service.create_artifact(
                    execution_id=execution_id,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    sandbox_id=sandbox_id,
                    file_path=file_path,
                    file_content=file_content,
                    message_id=message_id
                )
                
                if artifact_id:
                    import os
                    filename = os.path.basename(file_path)
                    
                    artifacts.append({
                        'artifact_id': artifact_id,
                        'filename': filename,
                        'file_path': file_path,
                        'size_bytes': len(file_content),
                        'execution_id': execution_id
                    })
                    logger.info(f"Created artifact {artifact_id} for file {file_path}")
                    
            except Exception as e:
                logger.error(f"Failed to process artifact {file_path}: {e}")
                continue
        
        return artifacts
    
    def _persist_output_async(self, execution_id, stdout, stderr, exit_code):
        """
        Asynchronously persist execution output to avoid blocking agent execution.
        This runs in a separate greenlet.
        """
        try:
            self.persistence_service.persist_execution_output(
                execution_id=execution_id,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code
            )
            logger.info(f"Persisted output for execution {execution_id}")
        except Exception as e:
            logger.error(f"Failed to persist output asynchronously: {e}")
    
    def _detect_and_emit_artifacts_async(self, sandbox_id, execution_id, files_before):
        """
        Asynchronously detect new files and emit artifact event to frontend.
        This runs in a separate greenlet to avoid blocking the chat.
        
        Args:
            sandbox_id: Sandbox ID
            execution_id: Execution ID
            files_before: Set of file paths before command execution
        """
        try:
            # Get files after execution
            files_after = self._get_sandbox_files(sandbox_id)
            new_files = files_after - files_before
            
            if not new_files:
                logger.info(f"No new files detected for execution {execution_id}")
                return
            
            logger.info(f"Detected {len(new_files)} new/modified files")
            
            # Process artifacts (download, upload to R2, store in DB)
            artifacts_data = self._process_artifacts(
                sandbox_id, execution_id, new_files, self.message_id
            )
            
            if not artifacts_data:
                logger.info(f"No artifacts created for execution {execution_id}")
                return
            
            # Emit separate socket event with artifact data
            if self.socketio and self._frontend_room():
                payload = self._attach_delegation_metadata({
                    "id": self.message_id,
                    "execution_id": execution_id,
                    "artifacts": artifacts_data
                })
                self.socketio.emit("sandbox-artifacts-created", payload, room=self._frontend_room())
                logger.info(f"Emitted artifact event with {len(artifacts_data)} artifacts")
            
        except Exception as e:
            logger.error(f"Failed to detect and emit artifacts: {e}", exc_info=True)
