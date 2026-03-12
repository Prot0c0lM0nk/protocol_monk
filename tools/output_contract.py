from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

TOOL_OUTPUT_SCHEMA_VERSION = "tool_output.v1"
DEFAULT_STREAM_CHAR_LIMIT = 4000


def build_tool_output(
    *,
    result_type: str,
    summary: str,
    data: Dict[str, Any],
    pagination: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": TOOL_OUTPUT_SCHEMA_VERSION,
        "result_type": result_type,
        "summary": summary,
        "data": data,
        "pagination": pagination,
    }


def count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def build_text_stream(
    text: str,
    *,
    char_limit: int = DEFAULT_STREAM_CHAR_LIMIT,
) -> Dict[str, Any]:
    normalized = str(text or "")
    returned_text = normalized[:char_limit]
    all_lines = normalized.splitlines()
    returned_lines = returned_text.splitlines()
    omitted_char_count = max(0, len(normalized) - len(returned_text))

    return {
        "line_count": len(all_lines),
        "char_count": len(normalized),
        "returned_line_count": len(returned_lines),
        "returned_char_count": len(returned_text),
        "truncated": omitted_char_count > 0,
        "omitted_char_count": omitted_char_count,
        "lines": [
            {"line_number": index + 1, "text": line}
            for index, line in enumerate(returned_lines)
        ],
    }


def utf8_byte_count(text: str) -> int:
    return len((text or "").encode("utf-8"))


def summarize_line_range(start: int, end: int) -> str:
    if start == end:
        return f"line {start}"
    return f"lines {start}-{end}"


def build_line_pagination(
    *,
    total_lines: int,
    returned_start: int,
    returned_end: int,
    page_size: int,
) -> Optional[Dict[str, Any]]:
    if total_lines <= 0 or returned_start <= 0 or returned_end <= 0 or page_size <= 0:
        return None

    has_previous = returned_start > 1
    has_next = returned_end < total_lines

    previous_page = None
    if has_previous:
        previous_end = returned_start - 1
        previous_start = max(1, previous_end - page_size + 1)
        previous_page = {
            "line_start": previous_start,
            "line_end": previous_end,
        }

    next_page = None
    if has_next:
        next_start = returned_end + 1
        next_end = min(total_lines, next_start + page_size - 1)
        next_page = {
            "line_start": next_start,
            "line_end": next_end,
        }

    return {
        "mode": "line_range",
        "page_size": page_size,
        "returned_range": {
            "line_start": returned_start,
            "line_end": returned_end,
        },
        "total_lines": total_lines,
        "has_previous_page": has_previous,
        "has_next_page": has_next,
        "previous_page": previous_page,
        "next_page": next_page,
    }


def _json_top_level_type(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "null"


def _json_item_count(value: Any) -> Optional[int]:
    if isinstance(value, (dict, list)):
        return len(value)
    return None


def _try_parse_json(text: str) -> Tuple[bool, Any]:
    normalized = str(text or "")
    stripped = normalized.strip()
    if not stripped:
        return False, None
    try:
        return True, json.loads(stripped)
    except json.JSONDecodeError:
        return False, None


def detect_json_stream_output(
    stdout: str,
    stderr: str,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    for source_stream, text in (("stdout", stdout), ("stderr", stderr)):
        parsed, value = _try_parse_json(text)
        if not parsed:
            continue
        return (
            "json",
            {
                "source_stream": source_stream,
                "format": "json",
                "top_level_type": _json_top_level_type(value),
                "item_count": _json_item_count(value),
                "value": value,
            },
        )
    return "plain_text", None


def build_process_output(
    *,
    result_type: str,
    summary: str,
    command: Any,
    cwd: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    extra_data: Optional[Dict[str, Any]] = None,
    parse_json_streams: bool = False,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
    }
    if extra_data:
        data.update(extra_data)
    if parse_json_streams:
        output_format, parsed_output = detect_json_stream_output(stdout, stderr)
        data["output_format"] = output_format
        data["parsed_output"] = parsed_output
    data["stdout"] = build_text_stream(stdout)
    data["stderr"] = build_text_stream(stderr)

    return build_tool_output(
        result_type=result_type,
        summary=summary,
        data=data,
        pagination=None,
    )


def build_git_operation_output(
    *,
    summary: str,
    operation: str,
    command: Any,
    cwd: str,
    exit_code: int,
    git_result: Dict[str, Any],
    stdout: str,
    stderr: str,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "operation": operation,
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
        "git_result": git_result,
        "stdout": build_text_stream(stdout),
        "stderr": build_text_stream(stderr),
    }
    return build_tool_output(
        result_type="git_operation",
        summary=summary,
        data=data,
        pagination=None,
    )
