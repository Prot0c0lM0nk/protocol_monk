#!/usr/bin/env python3
"""
Delete Lines Tool - Delete specific line numbers from a file.
"""

import logging
import os
from pathlib import Path
from typing import List

from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus


class DeleteLinesTool(BaseTool):
    """Tool for deleting specific line numbers from a file."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="delete_lines",
            description=(
                "[USE THIS FOR REMOVING CODE] Delete specific line numbers. "
                "Perfect for removing unused code, cleaning up, or refactoring."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working directory)",
                },
                "line_start": {
                    "type": "integer",
                    "description": "Starting line number to delete (1-based)",
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number to delete (1-based, inclusive)",
                },
            },
            required_params=["filepath", "line_start", "line_end"],
        )

    def _perform_write(self, path: Path, content: str):
        """Perform atomic write to file."""
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(content, encoding="utf-8")
        with temp_path.open("r") as f:
            os.fsync(f.fileno())
        os.replace(temp_path, path)
        with path.open("r") as f:
            os.fsync(f.fileno())

    def _generate_deletion_view(
        self,
        filepath: str,
        line_start: int,
        line_end: int,
        deleted_lines: List[str],
    ) -> str:
        """Create a visual summary of deleted lines."""
        msg = f"✅ Deleted lines {line_start}-{line_end} from {filepath}\n"
        msg += f"📝 Removed {len(deleted_lines)} line(s):\n"
        msg += "─" * 50 + "\n"

        for i, line in enumerate(deleted_lines):
            line_num = line_start + i
            msg += f"-{line_num:3}│ {line}\n"

        msg += "─" * 50
        return msg

    def execute(self, **kwargs) -> ToolResult:
        """Delete specific line range from a file."""
        filepath = kwargs.get("filepath")
        line_start = kwargs.get("line_start")
        line_end = kwargs.get("line_end")

        if not filepath or not line_start or not line_end:
            return ToolResult.invalid_params(
                "❌ Missing required params.",
                missing_params=["filepath", "line_start", "line_end"],
            )

        # 1. Security Check
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(
                f"🔒 File path blocked: {filepath} (Unsafe path)"
            )

        full_path = self.working_dir / filepath

        try:
            # 2. Read & Validate
            lines = full_path.read_text(encoding="utf-8").splitlines()
            start_idx = line_start - 1
            end_idx = line_end  # Inclusive end means exclusive slice end

            if start_idx < 0 or end_idx > len(lines) or start_idx >= end_idx:
                return ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Invalid range: {line_start}-{line_end} (File: {len(lines)} lines)",
                )

            # 3. Process Content
            deleted_lines = lines[start_idx:end_idx]
            updated_lines = lines[:start_idx] + lines[end_idx:]
            new_content = "\n".join(updated_lines)

            # Preserve trailing newline
            original_text = full_path.read_text(encoding="utf-8")
            if original_text.endswith("\n"):
                new_content += "\n"

            # 4. Atomic Write
            self._perform_write(full_path, new_content)

            # 5. Generate Result
            result_msg = self._generate_deletion_view(
                filepath, line_start, line_end, deleted_lines
            )
            return ToolResult.success_result(
                result_msg,
                data={
                    "filepath": filepath,
                    "line_start": line_start,
                    "line_end": line_end,
                    "deleted_line_count": len(deleted_lines),
                    "deleted_content": "\n".join(deleted_lines),
                },
            )

        except FileNotFoundError:
            return ToolResult.command_failed(
                f"❌ File not found: {filepath}", exit_code=1
            )
        except (PermissionError, IOError, OSError) as e:
            self.logger.warning("Permission/IO error for %s: %s", filepath, e)
            return ToolResult.security_blocked(
                f"🔒 Permission denied: {filepath}", reason=str(e)
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Unexpected error in %s: %s", filepath, e, exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")
