"""
ui/textual/tool_preview.py
Build rich pre-run tool previews for confirmation dialogs.
"""

from __future__ import annotations

import difflib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass(slots=True)
class ToolPreview:
    """Rendered preview payload for tool confirmation."""

    summary: str
    full_text: str
    syntax_hint: Optional[str] = None


SCRATCH_KEYS = {
    "content_from_scratch": "content",
    "new_content_from_scratch": "new_content",
}


def build_tool_preview(
    tool_name: str, tool_args: Dict[str, Any], working_dir: Optional[str] = None
) -> ToolPreview:
    """Construct a full preview body for a tool call."""
    resolved_args, scratch_notes = _resolve_scratch_args(tool_args or {}, working_dir)

    builder = _PREVIEW_BUILDERS.get(tool_name, _build_default_preview)
    summary, preview_body, syntax_hint = builder(tool_name, resolved_args, working_dir)

    sections = [f"Tool: {tool_name}", "", "Arguments:", _json_dump(resolved_args)]
    if scratch_notes:
        sections.extend(["", "Scratch Resolution:"])
        sections.extend(f"- {note}" for note in scratch_notes)
    if preview_body:
        sections.extend(["", "Preview:", preview_body])

    return ToolPreview(
        summary=summary,
        full_text="\n".join(sections),
        syntax_hint=syntax_hint,
    )


def _resolve_scratch_args(
    args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[Dict[str, Any], list[str]]:
    """Replace scratch references with full text when available."""
    resolved = deepcopy(args)
    notes: list[str] = []
    scratch_root = _scratch_root(working_dir)

    for source_key, target_key in SCRATCH_KEYS.items():
        scratch_id = resolved.get(source_key)
        if not isinstance(scratch_id, str):
            continue

        content = _read_scratch_content(scratch_root, scratch_id)
        if content is None:
            placeholder = f"<missing scratch content: {scratch_id}>"
            resolved[target_key] = placeholder
            notes.append(f"{source_key}={scratch_id} missing; used placeholder")
        else:
            resolved[target_key] = content
            notes.append(
                f"{source_key}={scratch_id} resolved to {len(content)} characters"
            )

    return resolved, notes


def _scratch_root(working_dir: Optional[str]) -> Optional[Path]:
    if not working_dir:
        return None
    try:
        return Path(working_dir).expanduser().resolve() / ".scratch"
    except Exception:
        return None


def _read_scratch_content(scratch_root: Optional[Path], scratch_id: str) -> Optional[str]:
    if not scratch_root:
        return None
    try:
        path = scratch_root / f"{scratch_id}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _build_execute_command_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name, working_dir
    command = str(args.get("command", "")).strip()
    summary = _truncate(f"Shell command: {command}" if command else "Shell command")
    return summary, f"$ {command}" if command else "(empty command)", "bash"


def _build_run_python_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name, working_dir
    script = str(args.get("script_content", ""))
    script_name = str(args.get("script_name", "temp_python_script.py"))
    summary = f"Python script: {script_name} ({len(script.splitlines())} lines)"
    return summary, script or "(empty script)", "python"


def _build_git_operation_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name, working_dir
    operation = str(args.get("operation", "status"))
    commit_message = str(args.get("commit_message", "AI assistant changes"))

    command_map = {
        "status": "git status",
        "add": "git add .",
        "commit": f"git commit -m {json.dumps(commit_message)}",
        "push": "git push",
        "pull": "git pull",
        "log": "git log --oneline -10",
    }
    command = command_map.get(operation, f"git {operation}")
    summary = f"Git operation: {operation}"
    return summary, f"$ {command}", "bash"


def _build_replace_lines_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name
    filepath = str(args.get("filepath", ""))
    start = int(args.get("line_start", 0) or 0)
    end = int(args.get("line_end", 0) or 0)
    new_content = str(args.get("new_content", ""))
    new_lines = new_content.splitlines()

    old_lines, error = _read_file_range(working_dir, filepath, start, end)
    if error:
        summary = f"Replace lines {start}-{end} in {filepath}".strip()
        return summary, error, "diff"

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{filepath}:{start}-{end} (before)",
            tofile=f"{filepath}:{start}-{end} (after)",
            lineterm="",
        )
    )
    preview = "\n".join(diff_lines) if diff_lines else "(No changes detected)"
    summary = f"Replace lines {start}-{end} in {filepath} ({len(old_lines)} -> {len(new_lines)})"
    return summary, preview, "diff"


def _build_delete_lines_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name
    filepath = str(args.get("filepath", ""))
    start = int(args.get("line_start", 0) or 0)
    end = int(args.get("line_end", 0) or 0)
    old_lines, error = _read_file_range(working_dir, filepath, start, end)

    if error:
        summary = f"Delete lines {start}-{end} from {filepath}".strip()
        return summary, error, "diff"

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            [],
            fromfile=f"{filepath}:{start}-{end} (before)",
            tofile=f"{filepath}:{start}-{end} (after)",
            lineterm="",
        )
    )
    preview = "\n".join(diff_lines) if diff_lines else "(No changes detected)"
    summary = f"Delete lines {start}-{end} from {filepath} ({len(old_lines)} removed)"
    return summary, preview, "diff"


def _build_insert_in_file_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name
    filepath = str(args.get("filepath", ""))
    anchor = str(args.get("after_line", ""))
    inserted_text = str(args.get("content", ""))
    inserted_lines = inserted_text.splitlines()

    lines, read_error = _safe_read_lines(working_dir, filepath)
    if read_error:
        summary = f"Insert content into {filepath}".strip()
        return summary, read_error, "diff"

    try:
        anchor_index = lines.index(anchor)
    except ValueError:
        anchor_index = -1

    if anchor_index < 0:
        preview_lines = [
            f"Anchor line not found in {filepath}:",
            anchor or "(empty anchor)",
            "",
            "Inserted content:",
        ]
        preview_lines.extend(f"+ {line}" for line in inserted_lines)
        summary = f"Insert into {filepath} (anchor missing)"
        return summary, "\n".join(preview_lines), "diff"

    line_no = anchor_index + 1
    preview_lines = [
        f"@@ {filepath}:{line_no} @@",
        f"  {line_no:4} | {lines[anchor_index]}",
    ]
    for offset, line in enumerate(inserted_lines, 1):
        preview_lines.append(f"+ {line_no + offset:4} | {line}")
    summary = f"Insert {len(inserted_lines)} lines into {filepath} after line {line_no}"
    return summary, "\n".join(preview_lines), "diff"


def _build_append_to_file_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name, working_dir
    filepath = str(args.get("filepath", ""))
    appended_text = str(args.get("content", ""))
    appended_lines = appended_text.splitlines()
    summary = f"Append {len(appended_lines)} lines to {filepath}".strip()
    preview = "\n".join(f"+ {line}" for line in appended_lines) or "(no content to append)"
    return summary, preview, "diff"


def _build_create_file_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del tool_name, working_dir
    filepath = str(args.get("filepath", ""))
    content = str(args.get("content", ""))
    summary = f"Create file: {filepath} ({len(content.splitlines())} lines)"
    return summary, content or "(empty file)", _infer_syntax_from_path(filepath)


def _build_default_preview(
    tool_name: str, args: Dict[str, Any], working_dir: Optional[str]
) -> Tuple[str, str, Optional[str]]:
    del working_dir
    summary = f"Tool call: {tool_name}"
    return summary, _json_dump(args), None


def _read_file_range(
    working_dir: Optional[str], filepath: str, line_start: int, line_end: int
) -> Tuple[list[str], str]:
    lines, read_error = _safe_read_lines(working_dir, filepath)
    if read_error:
        return [], read_error

    if line_start < 1 or line_end < line_start:
        return [], "Invalid range for preview."
    if line_end > len(lines):
        return [], f"Range {line_start}-{line_end} exceeds file length ({len(lines)})."

    return lines[line_start - 1 : line_end], ""


def _safe_read_lines(working_dir: Optional[str], filepath: str) -> Tuple[list[str], str]:
    if not filepath:
        return [], "Missing filepath."
    if not working_dir:
        return [], "Working directory unavailable for preview."

    try:
        root = Path(working_dir).expanduser().resolve()
        path = Path(filepath)
        full_path = path if path.is_absolute() else (root / path)
        full_path = full_path.resolve()
        if not full_path.exists():
            return [], f"File not found: {full_path}"
        text = full_path.read_text(encoding="utf-8")
        return text.splitlines(), ""
    except Exception as error:
        return [], f"Failed to read file for preview: {error}"


def _infer_syntax_from_path(filepath: str) -> Optional[str]:
    suffix = Path(filepath).suffix.lower()
    return {
        ".py": "python",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".diff": "diff",
        ".patch": "diff",
    }.get(suffix)


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, default=str)


def _truncate(text: str, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


_PREVIEW_BUILDERS = {
    "execute_command": _build_execute_command_preview,
    "run_python": _build_run_python_preview,
    "git_operation": _build_git_operation_preview,
    "replace_lines": _build_replace_lines_preview,
    "delete_lines": _build_delete_lines_preview,
    "insert_in_file": _build_insert_in_file_preview,
    "append_to_file": _build_append_to_file_preview,
    "create_file": _build_create_file_preview,
}
