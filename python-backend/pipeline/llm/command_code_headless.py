from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv


DEFAULT_COMMAND_CODE_MODEL_ID = "xiaomi/mimo-v2.5-pro"
DEFAULT_MAX_TURNS = 10
DEFAULT_TIMEOUT_SECONDS = 300
_ENV_LOADED = False


class CommandCodeHeadlessClient:
    """
    Thin wrapper around Command Code headless mode for text + image analysis.

    This is intentionally used only for stock/risk analyzers where we need a
    single prompt/response pass over workspace files and charts, not live tool
    execution through Agno.
    """

    def __init__(self) -> None:
        _load_env_files()
        self.cli_path = self._resolve_cli_path()
        self.api_key = os.getenv("COMMAND_CODE_API_KEY", "").strip()
        self.model_id = os.getenv("COMMAND_CODE_CLI_MODEL_ID", DEFAULT_COMMAND_CODE_MODEL_ID).strip()
        self.max_turns = _safe_int(os.getenv("COMMAND_CODE_CLI_MAX_TURNS"), DEFAULT_MAX_TURNS)
        self.timeout_seconds = _safe_int(os.getenv("COMMAND_CODE_CLI_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS)
        self.disable_telemetry = os.getenv("COMMAND_CODE_CLI_DISABLE_TELEMETRY", "1").strip() not in {"0", "false", "False"}
        self.repo_root = Path(__file__).resolve().parents[3]

    def is_available(self) -> bool:
        return bool(self.cli_path and self.api_key)

    def run_analysis(
        self,
        prompt: str,
        image_paths: Optional[Iterable[str]] = None,
        workdir: Optional[Path] = None,
        max_turns: Optional[int] = None,
    ) -> str:
        if not self.cli_path:
            raise RuntimeError(
                "command_code_cli_missing::Set COMMAND_CODE_CLI_PATH or install Command Code CLI "
                "(for example command-code.cmd / cmdc.cmd)."
            )
        if not self.api_key:
            raise RuntimeError("command_code_auth_missing::COMMAND_CODE_API_KEY is not set.")

        cwd = str((workdir or self.repo_root).resolve())
        final_prompt = self._build_prompt(prompt, image_paths or [])
        command = [
            self.cli_path,
            "-p",
            "-m",
            self.model_id,
            "--skip-onboarding",
            "--max-turns",
            str(max_turns or self.max_turns),
            "-t",
        ]

        env = os.environ.copy()
        env["COMMAND_CODE_API_KEY"] = self.api_key
        if self.disable_telemetry:
            env["DO_NOT_TRACK"] = "1"

        completed = subprocess.run(
            command,
            input=final_prompt,
            text=True,
            capture_output=True,
            cwd=cwd,
            env=env,
            timeout=self.timeout_seconds,
            check=False,
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if completed.returncode != 0:
            error_detail = stderr or stdout or f"exit_code={completed.returncode}"
            raise RuntimeError(f"command_code_cli_failed::{completed.returncode}::{error_detail}")
        if not stdout:
            raise RuntimeError(f"command_code_cli_empty_response::{stderr or 'no_output'}")
        return stdout

    def _build_prompt(self, prompt: str, image_paths: Iterable[str]) -> str:
        normalized_paths: List[str] = []
        for path_str in image_paths:
            try:
                path = Path(path_str).resolve()
            except Exception:
                path = Path(path_str)
            normalized_paths.append(path.as_posix())

        if not normalized_paths:
            return prompt

        image_section = "\n".join(f"- {path}" for path in normalized_paths)
        return (
            "You are running inside Command Code headless mode on a trading-system repository.\n"
            "Inspect the referenced image files directly from the workspace when the environment supports it.\n"
            "If you cannot visually render image pixels in the current headless environment, say so implicitly by using the supplied JSON/text metadata instead of stalling.\n"
            "Do not infer chart content only from filenames.\n"
            "Use the chart images when possible and the supplied JSON/text context as the fallback evidence base.\n"
            "Do not modify files or run commands unless strictly necessary.\n\n"
            "Chart image files to inspect:\n"
            f"{image_section}\n\n"
            f"{prompt}"
        )

    def _resolve_cli_path(self) -> Optional[str]:
        configured = os.getenv("COMMAND_CODE_CLI_PATH", "").strip()
        candidates = [configured] if configured else []

        appdata = os.getenv("APPDATA")
        if appdata:
            candidates.extend(
                [
                    str(Path(appdata) / "npm" / "command-code.cmd"),
                    str(Path(appdata) / "npm" / "cmdc.cmd"),
                ]
            )

        for candidate in ("command-code", "cmdc", "commandcode"):
            resolved = shutil.which(candidate)
            if resolved:
                candidates.append(resolved)

        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return None


def _load_env_files() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    backend_dir = Path(__file__).resolve().parents[2]
    root_dir = backend_dir.parent
    load_dotenv(root_dir / ".env", override=False)
    load_dotenv(backend_dir / ".env", override=False)
    _ENV_LOADED = True


def _safe_int(value: Optional[str], default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default
