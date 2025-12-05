#!/usr/bin/env python3
"""
Delete Lines Tool - Delete specific line numbers from a file.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

from tools.base import BaseTool, ExecutionStatus, ToolResult, ToolSchema


class DeleteLinesTool(BaseTool):
    """Tool for deleting specific line numbers from a file."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        """Return the tool schema."""
        return ToolSchema(
            name="delete_lines",
            description=(
                "[USE THIS FOR REMOVING CODE] Delete specific line numbers. "
                "Perfect for removing unused code, cleaning up, or refactoring."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working dir)",
                },
                "line_start": {
                    "type": "integer",
                    "description": "Starting line number to delete (1-based)",
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number to delete (1-based)",
                },
            },
            required_params=["filepath", "line_start", "line_end"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """Orchestrate the line deletion process."""
        # 1. Validate Inputs & Security
        filepath, start, end, error = self._validate_inputs(kwargs)
        if error:
            return error

        # 2. Process Logic (Read -> Delete -> Reassemble)
        # pylint: disable=unpacking-non-sequence
        new_content, deleted_lines, proc_error = self._process_deletion(
            filepath, start, end
        )
        if proc_error:
            return proc_error

        # 3. Perform Write
        write_error = self._perform_atomic_write(filepath, new_content)
        if write_error:
            return write_error

        # 4. Return Success
        return self._format_success(filepath, start, end, deleted_lines)

    def _validate_inputs(
        self, kwargs: dict
    ) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[ToolResult]]:
        """Extract and validate parameters."""
        filepath = kwargs.get("filepath")
        start = kwargs.get("line_start")
        end = kwargs.get("line_end")

        if not filepath or not start or not end:
            return (
                None,
                None,
                None,
                ToolResult.invalid_params(
                    "❌ Missing required params.",
                    missing_params=["filepath", "line_start", "line_end"],
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
                ToolResult.security_blocked(
                    f"🔒 File path blocked: {filepath} (Unsafe path)"
                ),
            )

        return filepath, start, end, None

    def _process_deletion(
        self, filepath: str, line_start: int, line_end: int
    ) -> Tuple[str, List[str], Optional[ToolResult]]:
        """Read file, remove lines, and reassemble content."""
        full_path = self.working_dir / filepath

        try:
            content = full_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (
                "",
                [],
                ToolResult.command_failed(
                    f"❌ File not found: {filepath}", exit_code=1
                ),
            )
        except OSError as e:
            return "", [], ToolResult.internal_error(f"❌ Error reading file: {e}")

        lines = content.splitlines()
        start_idx = line_start - 1
        end_idx = line_end

        if start_idx < 0 or end_idx > len(lines) or start_idx >= end_idx:
            return (
                "",
                [],
                ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Invalid range: {line_start}-{line_end} "
                    f"(File has {len(lines)} lines)",
                ),
            )

        deleted_lines = lines[start_idx:end_idx]
        updated_lines = lines[:start_idx] + lines[end_idx:]
        new_content = "\n".join(updated_lines)

        # Preserve trailing newline if original had it
        if content.endswith("\n") and updated_lines:
            new_content += "\n"

        return new_content, deleted_lines, None

    def _perform_atomic_write(
        self, filepath: str, content: str
    ) -> Optional[ToolResult]:
        """Perform robust atomic write."""
        full_path = self.working_dir / filepath
        temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")

        try:
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, full_path)
            return None
        except PermissionError as e:
            self.logger.warning("Permission denied writing %s: %s", filepath, e)
            return ToolResult.security_blocked(f"🔒 Permission denied: {filepath}")
        except OSError as e:
            self.logger.error("File system error writing %s: %s", filepath, e)
            return ToolResult.internal_error(f"❌ File system error: {e}")

    def _format_success(
        self, filepath: str, start: int, end: int, deleted_lines: List[str]
    ) -> ToolResult:
        """Create the success result with visualization."""
        msg_lines = [
            f"✅ Deleted lines {start}-{end} from {filepath}",
            f"📝 Removed {len(deleted_lines)} line(s):",
            "─" * 50,
        ]

        for i, line in enumerate(deleted_lines):
            msg_lines.append(f"-{start + i:3}│ {line}")

        msg_lines.append("─" * 50)

        return ToolResult.success_result(
            "\n".join(msg_lines),
            data={
                "filepath": filepath,
                "line_start": start,
                "line_end": end,
                "deleted_line_count": len(deleted_lines),
                "deleted_content": "\n".join(deleted_lines),
            },
        )
