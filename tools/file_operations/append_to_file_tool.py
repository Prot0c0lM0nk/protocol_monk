#!/usr/bin/env python3
"""
Append to File Tool - Tool for appending content to the end of a file.
"""

import logging
import os
from pathlib import Path
from typing import Tuple, Optional

from tools.base import BaseTool, ToolSchema, ToolResult
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class AppendToFileTool(BaseTool):
    """Tool for appending content to the end of a file without modifying existing content."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="append_to_file",
            description=(
                "[USE THIS FOR ADDING NEW CONTENT] Add content to the END of a file "
                "without modifying existing content. Perfect for adding new functions, "
                "classes, or configuration."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working directory)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to add (for small content).",
                },
                "content_from_memory": {
                    "type": "string",
                    "description": "Memory key containing content.",
                },
                "content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block.",
                },
            },
            required_params=["filepath"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """Orchestrate the append operation."""
        filepath = kwargs.get("filepath")
        if not filepath:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'filepath'", missing_params=["filepath"]
            )

        # 1. Resolve Content
        content, error = self._resolve_content(kwargs)
        if error:
            return error

        # 2. Security Check
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(
                f"🔒 File path blocked due to security policy: {filepath}",
                reason="Unsafe file path",
            )

        # 3. Perform Append
        return self._perform_append(filepath, content)

    def _resolve_content(self, kwargs: dict) -> Tuple[str, Optional[ToolResult]]:
        """Determine the content source."""
        content = kwargs.get("content")
        scratch_id = kwargs.get("content_from_scratch")
        memory_key = kwargs.get("content_from_memory")

        # Auto-stage inline content if it's too large
        if content:
            staged_id = auto_stage_large_content(content, self.working_dir)
            if staged_id:
                scratch_id = staged_id
                content = None

        if scratch_id:
            return self._read_scratch_file(scratch_id)

        if memory_key:
            return "", ToolResult.internal_error(
                "❌ The 'content_from_memory' feature is not supported in this version."
            )

        if not content:
            return "", ToolResult.invalid_params(
                "❌ Must provide content via 'content' or 'content_from_scratch'.",
                missing_params=["content"],
            )

        return content, None

    def _read_scratch_file(self, scratch_id: str) -> Tuple[str, Optional[ToolResult]]:
        """Read content from a staged scratch file."""
        scratch_path = self.working_dir / ".scratch" / f"{scratch_id}.txt"

        if not scratch_path.exists():
            return "", ToolResult.invalid_params(
                f"❌ Scratch file '{scratch_id}' not found.",
                missing_params=["content_from_scratch"],
            )

        try:
            return scratch_path.read_text(encoding="utf-8"), None
        except Exception as e:  # pylint: disable=broad-exception-caught
            return "", ToolResult.internal_error(f"❌ Failed to read scratch file: {e}")

    def _perform_append(self, filepath: str, content: str) -> ToolResult:
        """Read, format, and atomic write."""
        full_path = self.working_dir / filepath

        try:
            # Read existing
            if not full_path.exists():
                return ToolResult.command_failed(
                    f"❌ File not found: {filepath}", exit_code=1
                )

            existing_content = full_path.read_text(encoding="utf-8")

            # Merge
            new_content = self._calculate_new_content(existing_content, content)

            # Write
            self._atomic_write(full_path, new_content)

            return self._format_result(filepath, content)

        except PermissionError as e:
            self.logger.warning("Permission denied for %s: %s", filepath, e)
            return ToolResult.security_blocked(f"🔒 Permission denied: {filepath}")
        except OSError as e:
            self.logger.error("File system error appending %s: %s", filepath, e)
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Unexpected error in %s: %s", filepath, e, exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")

    def _calculate_new_content(self, existing: str, new_chunk: str) -> str:
        """Handle logic for separators/newlines."""
        separator = "\n"
        if existing and not existing.endswith("\n"):
            separator = "\n\n"  # Ensure separation if file didn't end with newline
        elif not existing:
            separator = ""  # No separator for empty files

        return existing + separator + new_chunk

    def _atomic_write(self, full_path: Path, content: str):
        """Perform safe atomic write."""
        temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, full_path)
        except Exception:
            if temp_path.exists():
                os.remove(temp_path)
            raise

    def _format_result(self, filepath: str, content: str) -> ToolResult:
        """Format the success message."""
        line_count = len(content.splitlines())
        msg = (
            f"✅ Appended {line_count} line(s) to {filepath}\n"
            f"📝 Added content:\n{'-' * 40}\n{content}\n{'-' * 40}"
        )
        return ToolResult.success_result(
            msg,
            data={
                "filepath": filepath,
                "lines_added": line_count,
                "added_content": content,
            },
        )
