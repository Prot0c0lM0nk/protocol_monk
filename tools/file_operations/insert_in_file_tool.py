#!/usr/bin/env python3
"""
Insert In File Tool - Insert content after a specific line in a file.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

from tools.base import BaseTool, ExecutionStatus, ToolResult, ToolSchema
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class InsertInFileTool(BaseTool):
    """Tool for inserting content after a specific line in a file."""

    def __init__(self, working_dir: Path, context_manager=None):
        super().__init__(working_dir)
        self.context_manager = context_manager
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        """Return the tool schema."""
        return ToolSchema(
            name="insert_in_file",
            description=(
                "[USE THIS FOR INSERTING IN MIDDLE] Insert content after a "
                "specific line. Perfect for adding imports, class methods, "
                "or code between lines."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working dir)",
                },
                "after_line": {
                    "type": "string",
                    "description": "Exact line content to insert after",
                },
                "content": {
                    "type": "string",
                    "description": "Content to insert.",
                },
                "content_from_memory": {
                    "type": "string",
                    "description": "Memory key containing the content.",
                },
                "content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block.",
                },
            },
            required_params=["filepath", "after_line"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """Orchestrate the insertion."""
        # 1. Validate & Resolve Content
        filepath, target_line, content, error = self._validate_inputs(kwargs)
        if error:
            return error

        # 2. Logic: Read -> Find -> Splice
        full_path = self.working_dir / filepath
        # pylint: disable=unpacking-non-sequence
        new_text, insert_idx, added_lines, logic_error = self._apply_insertion(
            full_path, target_line, content
        )
        if logic_error:
            return logic_error

        # 3. Write
        write_error = self._perform_atomic_write(full_path, new_text)
        if write_error:
            return write_error

        # 4. Result
        return self._format_success(
            filepath, insert_idx, added_lines, new_text.splitlines()
        )

    def _validate_inputs(
        self, kwargs: dict
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[ToolResult]]:
        """Validate parameters and resolve content source."""
        filepath = kwargs.get("filepath")
        target_line = kwargs.get("after_line")

        if not filepath or not target_line:
            return (
                None,
                None,
                None,
                ToolResult.invalid_params(
                    "❌ Missing required params.",
                    missing_params=["filepath", "after_line"],
                ),
            )

        # Path Cleaning
        str_cwd = str(self.working_dir)
        if str(filepath).startswith(str_cwd):
            filepath = str(filepath)[len(str_cwd) :].lstrip(os.sep)

        if not self._is_safe_file_path(filepath):
            return (
                None,
                None,
                None,
                ToolResult.security_blocked(f"🔒 File path blocked: {filepath}"),
            )

        content, error = self._resolve_content(**kwargs)
        if error:
            return None, None, None, error

        return filepath, target_line, content, None

    def _resolve_content(self, **kwargs) -> Tuple[Optional[str], Optional[ToolResult]]:
        """Resolve content from scratch, memory, or inline."""
        content = kwargs.get("content")
        memory_key = kwargs.get("content_from_memory")
        scratch_id = kwargs.get("content_from_scratch")

        if content:
            staged_id = auto_stage_large_content(content, self.working_dir)
            if staged_id:
                scratch_id = staged_id
                content = None

        if scratch_id:
            return self._read_scratch(scratch_id)

        if memory_key:
            return self._read_memory(memory_key)

        if content is not None:
            return content, None

        return None, ToolResult.invalid_params(
            "❌ Must provide content via inline, memory, or scratch.",
            missing_params=["content"],
        )

    def _read_scratch(
        self, scratch_id: str
    ) -> Tuple[Optional[str], Optional[ToolResult]]:
        path = self.working_dir / ".scratch" / f"{scratch_id}.txt"
        if not path.exists():
            return None, ToolResult.invalid_params(
                f"❌ Scratch file '{scratch_id}' not found."
            )
        try:
            return path.read_text(encoding="utf-8"), None
        except OSError as e:
            return None, ToolResult.internal_error(f"❌ Error reading scratch: {e}")

    def _read_memory(self, key: str) -> Tuple[Optional[str], Optional[ToolResult]]:
        if not self.context_manager:
            return None, ToolResult.internal_error("❌ Memory system unavailable.")
        if key not in self.context_manager.working_memory:
            return None, ToolResult.invalid_params(f"❌ Memory key '{key}' not found.")
        return self.context_manager.working_memory[key], None

    def _apply_insertion(
        self, full_path: Path, target_line: str, content: str
    ) -> Tuple[str, int, List[str], Optional[ToolResult]]:
        """Read file, find line, and insert content."""
        try:
            original_content = full_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (
                "",
                0,
                [],
                ToolResult.command_failed(
                    f"❌ File not found: {full_path.name}", exit_code=1
                ),
            )
        except OSError as e:
            return "", 0, [], ToolResult.internal_error(f"❌ Error reading file: {e}")

        lines = original_content.splitlines()

        # Find insertion index
        try:
            # We add 1 because we insert AFTER the line
            insert_idx = lines.index(target_line) + 1
        except ValueError:
            return (
                "",
                0,
                [],
                ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Target line not found: '{target_line}'",
                ),
            )

        new_lines_list = content.splitlines()
        updated_lines = lines[:insert_idx] + new_lines_list + lines[insert_idx:]

        new_text = "\n".join(updated_lines)
        if original_content.endswith("\n"):
            new_text += "\n"

        return new_text, insert_idx, new_lines_list, None

    def _perform_atomic_write(self, path: Path, content: str) -> Optional[ToolResult]:
        """Perform robust atomic write."""
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
            return None
        except OSError as e:
            self.logger.error("Error writing %s: %s", path, e)
            return ToolResult.internal_error(f"❌ File system error: {e}")

    def _format_success(
        self,
        filepath: str,
        insert_idx: int,
        added_lines: List[str],
        all_lines: List[str],
    ) -> ToolResult:
        """Create success result with context view."""
        msg = (
            f"✅ Inserted {len(added_lines)} line(s) after line "
            f"{insert_idx} in {filepath}\n"
            f"📝 Insertion context:\n{'-' * 50}\n"
        )

        context_range = 2
        start_show = max(0, insert_idx - context_range)
        end_show = min(len(all_lines), insert_idx + len(added_lines) + context_range)

        for i in range(start_show, end_show):
            line_num = i + 1
            line_content = all_lines[i]

            # Highlight inserted lines
            is_inserted = insert_idx <= i < insert_idx + len(added_lines)
            prefix = "+" if is_inserted else " "
            msg += f"{prefix}{line_num:3}│ {line_content}\n"

        msg += f"{'-' * 50}"

        return ToolResult.success_result(
            msg,
            data={
                "filepath": filepath,
                "insert_after_line": insert_idx,
                "lines_inserted": len(added_lines),
                "inserted_content": "\n".join(added_lines),
            },
        )
