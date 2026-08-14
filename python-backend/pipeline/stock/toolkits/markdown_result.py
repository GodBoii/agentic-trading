from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence


def tool_result_markdown(value: Any) -> str:
    """Render structured tool output as compact, deterministic Markdown for an LLM."""
    lines = ["## Tool result"]
    lines.extend(_render(value, 0))
    return "\n".join(lines)


def _render(value: Any, depth: int) -> list[str]:
    indent = "  " * depth
    if isinstance(value, Mapping):
        if not value:
            return [f"{indent}- none"]
        lines: list[str] = []
        for key, item in value.items():
            label = _text(key)
            if _is_scalar(item):
                lines.append(f"{indent}- {label}: {_scalar(item)}")
            else:
                lines.append(f"{indent}- {label}:")
                lines.extend(_render(item, depth + 1))
        return lines
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return [f"{indent}- none"]
        if _is_flat_table(value):
            return _table(value, depth)
        lines = []
        for item in value:
            if _is_scalar(item):
                lines.append(f"{indent}- {_scalar(item)}")
            else:
                lines.append(f"{indent}- item:")
                lines.extend(_render(item, depth + 1))
        return lines
    return [f"{indent}- {_scalar(value)}"]


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return format(value, ".15g")
    if isinstance(value, (int,)):
        return str(value)
    return _text(value)


def _text(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>").replace("|", "\\|")


def _is_flat_table(value: Sequence[Any]) -> bool:
    return len(value) > 1 and all(
        isinstance(row, Mapping) and row and all(_is_scalar(cell) for cell in row.values())
        for row in value
    )


def _table(value: Sequence[Mapping[str, Any]], depth: int) -> list[str]:
    indent = "  " * depth
    columns: list[str] = []
    for row in value:
        for key in row:
            label = str(key)
            if label not in columns:
                columns.append(label)
    header = f"{indent}| " + " | ".join(_text(key) for key in columns) + " |"
    separator = f"{indent}| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        f"{indent}| " + " | ".join(_scalar(row.get(key)) for key in columns) + " |"
        for row in value
    ]
    return [header, separator, *rows]


def json_tool_result_markdown(value: str) -> str:
    """Convert an internal JSON tool response to Markdown, retaining plain failures."""
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        parsed = {"status": "failure", "remarks": str(value)}
    return tool_result_markdown(parsed)
