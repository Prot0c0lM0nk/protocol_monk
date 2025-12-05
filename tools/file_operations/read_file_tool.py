#!/usr/bin/env python3
"""
Read File Tool - Tool for reading specific lines from a file.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

from tools.base import BaseTool, ExecutionStatus, ToolResult, ToolSchema


class ReadFileTool(BaseTool):
    """Tool for reading specific lines from a file."""

    MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024  # 1 MB limit

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        """Return the tool schema."""
        return ToolSchema(
            name="read_file",
            description="Read and display file contents, with optional line range.",
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to show",
                },
                "line_start": {
                    "type": "integer",
                    "description": "Starting line number (1-based, optional).",
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number (1-based, optional).",
                },
            },
            required_params=["filepath"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """Orchestrate the read operation."""
        filepath = kwargs.get("filepath")
        if not filepath:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'filepath'", missing_params=["filepath"]
            )

        # Path Cleaning: Remove redundant working_dir prefix
        str_cwd = str(self.working_dir)
        if str(filepath).startswith(str_cwd):
            filepath = str(filepath)[len(str_cwd) :].lstrip(os.sep)

        # 1. Read File
        lines, error = self._validate_and_read(filepath)
        if error:
            return error

        # 2. Extract Range
        start, end = kwargs.get("line_start"), kwargs.get("line_end")
        # pylint: disable=unpacking-non-sequence
        selected_lines, actual_start, actual_end, range_error = self._extract_range(
            lines, start, end
        )

        if range_error:
            return range_error

        # 3. Format Output
        return self._format_output(filepath, selected_lines, actual_start, actual_end)

    def _validate_and_read(
        self, filepath: str
    ) -> Tuple[List[str], Optional[ToolResult]]:
        """Validate path, check size, and read content."""
        if not self._is_safe_file_path(filepath):
            return [], ToolResult.security_blocked(
                f"🔒 File path blocked due to security policy: {filepath}",
                reason="Unsafe file path",
            )

        full_path = self.working_dir / filepath

        try:
            if not full_path.exists():
                return [], ToolResult.command_failed(
                    f"❌ File not found: {filepath}", exit_code=1
                )

            if full_path.stat().st_size > self.MAX_FILE_SIZE_BYTES:
                size_kb = self.MAX_FILE_SIZE_BYTES / 1024
                return [], ToolResult.command_failed(
                    f"❌ File too large (> {size_kb:.2f} KB).",
                    exit_code=1,
                )

            content = full_path.read_text(encoding="utf-8")
            return content.splitlines(), None

        except PermissionError as e:
            self.logger.warning("Permission denied for %s: %s", filepath, e)
            return [], ToolResult.security_blocked(f"🔒 Permission denied: {filepath}")
        except UnicodeDecodeError as e:
            return [], ToolResult.internal_error(
                f"❌ Encoding error: {e}. File may be binary."
            )
        except OSError as e:
            self.logger.error("File system error reading %s: %s", filepath, e)
            return [], ToolResult.internal_error(f"❌ File system error: {e}")

    def _extract_range(
        self, lines: List[str], start: Optional[int], end: Optional[int]
    ) -> Tuple[List[str], int, int, Optional[ToolResult]]:
        """Slice the lines based on requested range."""
        total_lines = len(lines)

        # Default to full file if not specified
        start_idx = (start - 1) if start else 0
        end_idx = end if end else total_lines

        # Clamp range
        start_idx = max(0, start_idx)
        end_idx = min(total_lines, end_idx)

        if start and start_idx >= total_lines:
            return (
                [],
                0,
                0,
                ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Start line {start} exceeds length ({total_lines})",
                ),
            )

        return lines[start_idx:end_idx], start_idx + 1, end_idx, None

    def _format_output(
        self, filepath: str, lines: List[str], start: int, end: int
    ) -> ToolResult:
        """Create the formatted display string."""
        numbered_content = "\n".join(
            f"{i+start:3}│ {line}" for i, line in enumerate(lines)
        )

        output = (
            f"📄 File {filepath} (lines {start}-{end}):\n"
            f"{'─' * 60}\n{numbered_content}\n{'─' * 60}"
        )

        return ToolResult.success_result(
            output,
            data={
                "filepath": filepath,
                "line_start": start,
                "line_end": end,
                "content": "\n".join(lines),
            },
        )
