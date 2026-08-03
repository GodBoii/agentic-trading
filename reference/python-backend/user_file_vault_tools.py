import json
import logging
from typing import Optional

from agno.tools import Toolkit

from user_file_vault import (
    delete_user_file,
    get_user_file,
    list_user_files,
    read_user_file_text,
)

logger = logging.getLogger(__name__)


class UserFileVaultTools(Toolkit):
    """
    Toolkit for persistent user-managed file vault.
    """

    def __init__(self, user_id: str):
        super().__init__(
            name="user_file_vault_tools",
            tools=[
                self.list_user_files,
                self.get_file_details,
                self.read_user_file,
                self.delete_user_file,
            ],
        )
        self.user_id = str(user_id)

    def list_user_files(self, search: str = "", file_type: str = "all", limit: int = 50) -> str:
        try:
            rows = list_user_files(
                user_id=self.user_id,
                limit=limit,
                search=str(search or "").strip(),
                file_type=str(file_type or "all").strip().lower(),
                signed_url_expiry=3600,
            )
            return json.dumps({"ok": True, "files": rows, "count": len(rows)}, ensure_ascii=True, default=str)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def get_file_details(self, file_id: str) -> str:
        try:
            if not str(file_id or "").strip():
                raise ValueError("file_id is required")
            row = get_user_file(user_id=self.user_id, file_id=str(file_id), include_signed_url=True)
            return json.dumps({"ok": True, "file": row}, ensure_ascii=True, default=str)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def read_user_file(self, file_id: str, max_chars: int = 40000) -> str:
        try:
            if not str(file_id or "").strip():
                raise ValueError("file_id is required")
            row = read_user_file_text(user_id=self.user_id, file_id=str(file_id), max_chars=max_chars)
            return json.dumps({"ok": True, "file": row}, ensure_ascii=True, default=str)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)

    def delete_user_file(self, file_id: str, confirm: bool = False) -> str:
        try:
            if not str(file_id or "").strip():
                raise ValueError("file_id is required")
            if not confirm:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "Set confirm=true to delete file permanently",
                        "requires_confirmation": True,
                    },
                    ensure_ascii=True,
                )
            result = delete_user_file(user_id=self.user_id, file_id=str(file_id))
            return json.dumps({"ok": True, **result}, ensure_ascii=True)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True)
