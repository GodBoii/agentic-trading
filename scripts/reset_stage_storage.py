#!/usr/bin/env python3
"""Delete local Stage 1/Stage 2 snapshots and supervisor state safely."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = (ROOT / "python-backend").resolve()
STAGE_PATTERN = re.compile(r"^stage[12](?:[-_].*)?\.json$")
STATE_FILES = {
    "session_supervisor_state.json",
    "session_supervisor_status.json",
}


def main() -> int:
    targets = [
        path.resolve()
        for path in BACKEND.iterdir()
        if path.is_file()
        and (STAGE_PATTERN.fullmatch(path.name) or path.name in STATE_FILES)
    ]
    for target in targets:
        if target.parent != BACKEND:
            raise RuntimeError(f"Refusing to delete outside backend directory: {target}")

    for target in targets:
        target.unlink()

    print(f"Deleted {len(targets)} Stage 1/Stage 2 and supervisor-state files.")
    for target in sorted(targets):
        print(target.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
