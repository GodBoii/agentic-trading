import json
import logging
import uuid
from typing import Any, Dict, Optional

from redis import Redis

from agno.tools import Toolkit

logger = logging.getLogger(__name__)


class LocalCoderTools(Toolkit):
    """
    Local coder toolkit that executes filesystem/git/terminal operations through
    the Electron desktop bridge (Socket.IO + Redis pub/sub).
    """

    def __init__(
        self,
        sid: str,
        socketio,
        redis_client: Redis,
        workspace_root: Optional[str] = None,
        **kwargs,
    ):
        self.sid = sid
        self.socketio = socketio
        self.redis_client = redis_client
        self.workspace_root = workspace_root
        self.message_id = kwargs.pop("message_id", None)
        self.conversation_id = kwargs.pop("conversation_id", None)
        self.delegation_id = kwargs.pop("delegation_id", None)
        self.delegated_agent = kwargs.pop("delegated_agent", None)

        super().__init__(
            name="local_coder_tools",
            tools=[
                self.get_workspace_overview,
                self.list_files,
                self.search_code,
                self.read_file,
                self.write_file,
                self.edit_file,
                self.create_file,
                self.delete_path,
                self.move_path,
                self.execute_local_command,
                self.git_status,
                self.git_branches,
                self.git_diff,
                self.git_log,
            ],
        )

    def _frontend_room(self) -> Optional[str]:
        if self.conversation_id:
            return f"conv:{self.conversation_id}"
        return self.sid

    def _send_command_and_wait(self, command_payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.sid or not self.socketio or not self.redis_client:
            return {
                "status": "error",
                "error": "Local coder bridge is unavailable in this session/device.",
            }

        request_id = str(uuid.uuid4())
        command_payload["request_id"] = request_id
        if self.message_id:
            command_payload["message_id"] = self.message_id
        if self.conversation_id:
            command_payload["conversation_id"] = self.conversation_id
        if self.workspace_root:
            command_payload["root_path"] = self.workspace_root
        if self.delegation_id:
            command_payload["delegation_id"] = self.delegation_id
        if self.delegated_agent:
            command_payload["delegated_agent"] = self.delegated_agent

        response_channel = f"local-coder-response:{request_id}"
        pubsub = self.redis_client.pubsub()

        try:
            pubsub.subscribe(response_channel)
            self.socketio.emit("local-coder-command", command_payload, room=self.sid)

            for message in pubsub.listen():
                if message["type"] == "message":
                    data = message.get("data")
                    if not data:
                        return {"status": "error", "error": "Empty bridge response"}
                    if isinstance(data, bytes):
                        data = data.decode("utf-8", errors="ignore")
                    return json.loads(data)
        except Exception as e:
            logger.error("Local coder bridge error: %s", e, exc_info=True)
            return {"status": "error", "error": f"Bridge error: {e}"}
        finally:
            pubsub.unsubscribe(response_channel)
            pubsub.close()

    def _emit_command_started(self, command: str) -> None:
        room_name = self._frontend_room()
        if not room_name:
            return
        self.socketio.emit(
            "local-command-started",
            {
                "id": self.message_id,
                "command": command,
                "delegation_id": self.delegation_id,
                "delegated_agent": self.delegated_agent,
            },
            room=room_name,
        )

    def _emit_command_finished(self, command: str, result: Dict[str, Any]) -> None:
        room_name = self._frontend_room()
        if not room_name:
            return

        exit_code = result.get("exit_code", 0 if result.get("status") == "success" else 1)
        self.socketio.emit(
            "local-command-finished",
            {
                "id": self.message_id,
                "command": command,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "exit_code": exit_code,
                "delegation_id": self.delegation_id,
                "delegated_agent": self.delegated_agent,
            },
            room=room_name,
        )

    @staticmethod
    def _format_result(result: Dict[str, Any]) -> str:
        if result.get("status") == "error":
            return f"Error: {result.get('error', 'Unknown error')}"
        return json.dumps(result, ensure_ascii=True, indent=2)

    def get_workspace_overview(self) -> str:
        result = self._send_command_and_wait({"action": "workspace_overview"})
        return self._format_result(result)

    def list_files(self, path: str = ".") -> str:
        result = self._send_command_and_wait({"action": "list_files", "path": path})
        return self._format_result(result)

    def search_code(self, query: str, max_results: int = 100) -> str:
        result = self._send_command_and_wait(
            {"action": "search_code", "query": query, "max_results": max_results}
        )
        return self._format_result(result)

    def read_file(self, path: str) -> str:
        result = self._send_command_and_wait({"action": "read_file", "path": path})
        return self._format_result(result)

    def write_file(self, path: str, content: str) -> str:
        result = self._send_command_and_wait(
            {"action": "write_file", "path": path, "content": content}
        )
        return self._format_result(result)

    def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        result = self._send_command_and_wait(
            {
                "action": "edit_file",
                "path": path,
                "old_text": old_text,
                "new_text": new_text,
                "replace_all": replace_all,
            }
        )
        return self._format_result(result)

    def create_file(self, path: str, content: str = "", overwrite: bool = False) -> str:
        result = self._send_command_and_wait(
            {
                "action": "create_file",
                "path": path,
                "content": content,
                "overwrite": overwrite,
            }
        )
        return self._format_result(result)

    def delete_path(self, path: str) -> str:
        result = self._send_command_and_wait({"action": "delete_path", "path": path})
        return self._format_result(result)

    def move_path(self, from_path: str, to_path: str) -> str:
        result = self._send_command_and_wait(
            {"action": "move_path", "from_path": from_path, "to_path": to_path}
        )
        return self._format_result(result)

    def execute_local_command(self, command: str, timeout_ms: int = 120000) -> str:
        self._emit_command_started(command)
        result = self._send_command_and_wait(
            {"action": "execute_command", "command": command, "timeout_ms": timeout_ms}
        )
        self._emit_command_finished(command, result)
        return self._format_result(result)

    def git_status(self) -> str:
        result = self._send_command_and_wait({"action": "git_status"})
        return self._format_result(result)

    def git_branches(self) -> str:
        result = self._send_command_and_wait({"action": "git_branches"})
        return self._format_result(result)

    def git_diff(self, target: str = "") -> str:
        result = self._send_command_and_wait({"action": "git_diff", "target": target})
        return self._format_result(result)

    def git_log(self, limit: int = 20) -> str:
        result = self._send_command_and_wait({"action": "git_log", "limit": limit})
        return self._format_result(result)
