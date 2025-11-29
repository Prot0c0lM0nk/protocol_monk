#!/usr/bin/env python3
"""
Delete Lines Tool - Delete specific line numbers from a file.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any

from agent import exceptions
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
            description="[USE THIS FOR REMOVING CODE] Delete specific line numbers. Perfect for removing unused code, cleaning up, or refactoring.",
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

    def execute(self, **kwargs) -> ToolResult:
        """Delete specific line range from a file."""
        filepath = kwargs.get("filepath")
        line_start = kwargs.get("line_start")
        line_end = kwargs.get("line_end")

        # Validate required parameters
        if not filepath:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'filepath'", missing_params=["filepath"]
            )
        if not line_start:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'line_start'",
                missing_params=["line_start"],
            )
        if not line_end:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'line_end'", missing_params=["line_end"]
            )

        # Security validation
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(
                f"🔒 File path blocked due to security policy: {filepath}",
                reason="Unsafe file path",
            )

        full_path = self.working_dir / filepath

        try:
            # Read existing content
            lines = full_path.read_text(encoding="utf-8").splitlines()

            # Validate line range (convert to 0-based indexing)
            start_idx = line_start - 1
            end_idx = (
                line_end  # This becomes exclusive in slicing, making line_end inclusive
            )

            if start_idx < 0 or end_idx > len(lines) or start_idx >= end_idx:
                return ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Invalid line range: {line_start}-{line_end}. File has {len(lines)} lines.",
                )

            # Get lines to delete for display
            deleted_lines = lines[start_idx:end_idx]

            # Create new content without the deleted lines
            updated_lines = lines[:start_idx] + lines[end_idx:]
            new_content = "\n".join(updated_lines)

            # Preserve trailing newline if original file had one
            original_content = full_path.read_text(encoding="utf-8")
            if original_content and original_content.endswith("\n"):
                new_content += "\n"

            # Atomic write
            temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")
            temp_path.write_text(new_content, encoding="utf-8")

            with temp_path.open("r") as f:
                os.fsync(f.fileno())

            os.replace(temp_path, full_path)

            with full_path.open("r") as f:
                os.fsync(f.fileno())

            # Show deletion summary
            result_message = (
                f"✅ Deleted lines {line_start}-{line_end} from {filepath}\n"
            )
            result_message += f"📝 Removed {len(deleted_lines)} line(s):\n"
            result_message += "─" * 50 + "\n"

            # Show deleted lines
            for i, line in enumerate(deleted_lines):
                line_num = line_start + i
                result_message += f"-{line_num:3}│ {line}\n"

            result_message += "─" * 50

            return ToolResult.success_result(
                result_message,
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
        except PermissionError as e:
            self.logger.warning(f"Permission denied for {filepath}: {e}", exc_info=True)
            return ToolResult.security_blocked(
                f"🔒 Permission denied: Cannot write to {filepath}.", reason=str(e)
            )
        except UnicodeDecodeError as e:
            return ToolResult.internal_error(
                f"❌ Encoding error: Cannot read {filepath} as 'utf-8'. It may be a binary file. Error: {e}"
            )
        except UnicodeEncodeError as e:
            return ToolResult.internal_error(
                f"❌ Encoding error: Cannot write new content to {filepath} as 'utf-8'. Error: {e}"
            )
        except (IOError, OSError) as e:
            self.logger.error(
                f"File system error deleting lines in {filepath}: {e}", exc_info=True
            )
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:
            self.logger.error(
                f"Unexpected error deleting lines in {filepath}: {e}", exc_info=True
            )
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")
