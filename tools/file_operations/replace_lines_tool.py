#!/usr/bin/env python3
"""
Replace Lines Tool - Replace specific line numbers in a file.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple, List

from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class ReplaceLinesTool(BaseTool):
    """Tool for replacing specific line numbers in a file."""

    def __init__(self, working_dir: Path, context_manager=None):
        super().__init__(working_dir)
        self.context_manager = context_manager
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="replace_lines",
            description=(
                "[DANGER] Deletes all lines from 'line_start' to 'line_end' (inclusive) "
                "and inserts 'new_content'. Use 'read_file' first."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working directory)",
                },
                "line_start": {
                    "type": "integer",
                    "description": "Starting line number to replace (1-based)",
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number to replace (1-based, inclusive)",
                },
                "new_content": {
                    "type": "string",
                    "description": "New content (for small updates).",
                },
                "new_content_from_memory": {
                    "type": "string",
                    "description": "Memory key for large content.",
                },
                "new_content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code blocks.",
                },
            },
            required_params=["filepath", "line_start", "line_end"],
        )

    def _resolve_content(self, **kwargs) -> Tuple[Optional[str], Optional[ToolResult]]:
        """Resolve content from scratch, memory, or inline."""
        new_content = kwargs.get("new_content")
        new_content_from_memory = kwargs.get("new_content_from_memory")
        new_content_from_scratch = kwargs.get("new_content_from_scratch")

        # Auto-stage if inline content is too large
        if new_content:
            staged_id = auto_stage_large_content(new_content, self.working_dir)
            if staged_id:
                new_content_from_scratch = staged_id
                new_content = None

        # 1. From Scratch
        if new_content_from_scratch:
            scratch_path = (
                self.working_dir / ".scratch" / f"{new_content_from_scratch}.txt"
            )
            if not scratch_path.exists():
                return None, ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Scratch file '{new_content_from_scratch}' not found.",
                )
            try:
                return scratch_path.read_text(encoding="utf-8"), None
            except Exception as e:  # pylint: disable=broad-exception-caught
                return None, ToolResult(
                    ExecutionStatus.INTERNAL_ERROR,
                    f"❌ Failed to read scratch file: {e}",
                )

        # 2. From Memory
        if new_content_from_memory:
            if not self.context_manager:
                return None, ToolResult(
                    ExecutionStatus.INTERNAL_ERROR,
                    "❌ Memory system not available.",
                )
            if new_content_from_memory not in self.context_manager.working_memory:
                return None, ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Memory key '{new_content_from_memory}' not found.",
                )
            return self.context_manager.working_memory[new_content_from_memory], None

        # 3. Inline
        if new_content is not None:
            return new_content, None

        return None, ToolResult.invalid_params(
            "❌ Must provide content source (inline, memory, or scratch).",
            missing_params=["new_content"],
        )

    def _generate_diff(
        self,
        filepath: str,
        line_start: int,
        line_end: int,
        old_lines: List[str],
        new_lines: List[str],
    ) -> str:
        """Create a visual diff of the changes."""
        msg = f"✅ Replaced lines {line_start}-{line_end} in {filepath}\n"
        msg += f"📝 Changes ({len(old_lines)} → {len(new_lines)} lines):\n"
        msg += "─" * 50 + "\n"

        for i, line in enumerate(old_lines):
            msg += f"-{line_start + i:3}│ {line}\n"

        for i, line in enumerate(new_lines):
            msg += f"+{line_start + i:3}│ {line}\n"

        msg += "─" * 50
        return msg

    def _perform_write(self, path: Path, content: str):
        """Perform atomic write to file."""
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(content, encoding="utf-8")
        with temp_path.open("r") as f:
            os.fsync(f.fileno())
        os.replace(temp_path, path)
        with path.open("r") as f:
            os.fsync(f.fileno())

    def execute(self, **kwargs) -> ToolResult:
        """Replace specific line range in a file."""
        filepath = kwargs.get("filepath")
        line_start = kwargs.get("line_start")
        line_end = kwargs.get("line_end")

        if not filepath or not line_start or not line_end:
            return ToolResult.invalid_params(
                "❌ Missing required params.",
                missing_params=["filepath", "line_start", "line_end"],
            )

        # 1. Resolve Content
        new_content, error = self._resolve_content(**kwargs)
        if error:
            return error

        # 2. Security Check
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(
                f"🔒 File path blocked: {filepath} (Unsafe path)"
            )

        full_path = self.working_dir / filepath

        try:
            # 3. Read & Validate
            lines = full_path.read_text(encoding="utf-8").splitlines()
            start_idx = line_start - 1
            end_idx = line_end  # Inclusive in user mind, exclusive in slice

            if start_idx < 0 or end_idx > len(lines) or start_idx >= end_idx:
                return ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Invalid range: {line_start}-{line_end} (File: {len(lines)} lines)",
                )

            # 4. Replace
            old_lines = lines[start_idx:end_idx]
            new_lines = new_content.splitlines()
            updated_lines = lines[:start_idx] + new_lines + lines[end_idx:]
            new_content_full = "\n".join(updated_lines)

            # Preserve trailing newline
            original_text = full_path.read_text(encoding="utf-8")
            if original_text.endswith("\n"):
                new_content_full += "\n"

            # 5. Atomic Write
            self._perform_write(full_path, new_content_full)

            # 6. Result
            result_msg = self._generate_diff(
                filepath, line_start, line_end, old_lines, new_lines
            )
            return ToolResult.success_result(
                result_msg,
                data={
                    "filepath": filepath,
                    "line_start": line_start,
                    "line_end": line_end,
                    "old_content": "\n".join(old_lines),
                    "new_content": new_content,
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
