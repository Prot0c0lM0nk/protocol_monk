#!/usr/bin/env python3
"""
Insert In File Tool - Insert content after a specific line in a file.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple, List

from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class InsertInFileTool(BaseTool):
    """Tool for inserting content after a specific line in a file."""

    def __init__(self, working_dir: Path, context_manager=None):
        super().__init__(working_dir)
        self.context_manager = context_manager
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="insert_in_file",
            description=(
                "[USE THIS FOR INSERTING IN MIDDLE] Insert content after a specific line. "
                "Perfect for adding imports, class methods, or code between lines."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working directory)",
                },
                "after_line": {
                    "type": "string",
                    "description": "Exact line content to insert after (must match exactly)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to insert (for small content).",
                },
                "content_from_memory": {
                    "type": "string",
                    "description": "Memory key containing the content to insert.",
                },
                "content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block.",
                },
            },
            required_params=["filepath", "after_line"],
        )

    def _resolve_content(self, **kwargs) -> Tuple[Optional[str], Optional[ToolResult]]:
        """Resolve content from scratch, memory, or inline."""
        content = kwargs.get("content")
        content_from_memory = kwargs.get("content_from_memory")
        content_from_scratch = kwargs.get("content_from_scratch")

        # Auto-stage if inline content is too large
        if content:
            staged_id = auto_stage_large_content(content, self.working_dir)
            if staged_id:
                content_from_scratch = staged_id
                content = None

        # 1. From Scratch
        if content_from_scratch:
            scratch_path = self.working_dir / ".scratch" / f"{content_from_scratch}.txt"
            if not scratch_path.exists():
                return None, ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Scratch file '{content_from_scratch}' not found.",
                )
            try:
                return scratch_path.read_text(encoding="utf-8"), None
            except Exception as e:  # pylint: disable=broad-exception-caught
                return None, ToolResult(
                    ExecutionStatus.INTERNAL_ERROR,
                    f"❌ Failed to read scratch file: {e}",
                )

        # 2. From Memory
        if content_from_memory:
            if not self.context_manager:
                return None, ToolResult(
                    ExecutionStatus.INTERNAL_ERROR,
                    "❌ Memory system not available.",
                )
            if content_from_memory not in self.context_manager.working_memory:
                return None, ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Memory key '{content_from_memory}' not found.",
                )
            return self.context_manager.working_memory[content_from_memory], None

        # 3. Inline
        if content is not None:
            return content, None

        return None, ToolResult.invalid_params(
            "❌ Must provide content source (inline, memory, or scratch).",
            missing_params=["content"],
        )

    def _find_insertion_line(self, lines: List[str], target_line: str) -> int:
        """Find the index to insert after."""
        for i, line in enumerate(lines):
            if line == target_line:
                return i + 1  # Insert AFTER this line
        return -1

    def _perform_write(self, path: Path, content: str):
        """Perform atomic write to file."""
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)

    def _generate_insertion_view(
        self,
        filepath: str,
        insert_index: int,
        content_lines: List[str],
        all_lines: List[str],
    ) -> str:
        """Create a visual context of the insertion."""
        msg = f"✅ Inserted {len(content_lines)} line(s) after line {insert_index} in {filepath}\n"
        msg += f"📝 Insertion context:\n{'-' * 50}\n"

        context_range = 2
        start_show = max(0, insert_index - context_range)
        # Total lines now includes inserted content
        end_show = min(
            len(all_lines), insert_index + len(content_lines) + context_range
        )

        for i in range(start_show, end_show):
            line_num = i + 1
            line_content = all_lines[i]

            # Check if this index corresponds to the newly inserted block
            # The inserted block starts at insert_index
            if insert_index <= i < insert_index + len(content_lines):
                msg += f"+{line_num:3}│ {line_content}\n"
            else:
                msg += f" {line_num:3}│ {line_content}\n"

        msg += f"{'-' * 50}"
        return msg

    def execute(self, **kwargs) -> ToolResult:
        """Insert content after a specific line in a file."""
        filepath = kwargs.get("filepath")
        after_line = kwargs.get("after_line")

        if not filepath or not after_line:
            return ToolResult.invalid_params(
                "❌ Missing required params.", missing_params=["filepath", "after_line"]
            )

        # 1. Resolve Content
        content, error = self._resolve_content(**kwargs)
        if error:
            return error

        # 2. Security Check
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(
                f"🔒 File path blocked: {filepath} (Unsafe path)"
            )

        full_path = self.working_dir / filepath

        try:
            # 3. Read File
            lines = full_path.read_text(encoding="utf-8").splitlines()

            # 4. Find Location
            insert_index = self._find_insertion_line(lines, after_line)
            if insert_index == -1:
                return ToolResult(
                    ExecutionStatus.COMMAND_FAILED, f"❌ Line not found: '{after_line}'"
                )

            # 5. Modify Content
            content_lines = content.splitlines()
            new_lines = lines[:insert_index] + content_lines + lines[insert_index:]
            new_content_full = "\n".join(new_lines)

            # 6. Atomic Write
            self._perform_write(full_path, new_content_full)

            # 7. Generate Result
            result_msg = self._generate_insertion_view(
                filepath, insert_index, content_lines, new_lines
            )

            return ToolResult.success_result(
                result_msg,
                data={
                    "filepath": filepath,
                    "insert_after_line": insert_index,
                    "lines_inserted": len(content_lines),
                    "inserted_content": content,
                },
            )

        except FileNotFoundError:
            return ToolResult.command_failed(
                f"❌ File not found: {filepath}", exit_code=1
            )
        except (PermissionError, IOError, OSError) as e:
            self.logger.error("File error in %s: %s", filepath, e, exc_info=True)
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Unexpected error in %s: %s", filepath, e, exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")
