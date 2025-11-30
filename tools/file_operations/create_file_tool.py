#!/usr/bin/env python3
"""
Create File Tool - Tool for creating new files with content.
"""

import os
import logging
from pathlib import Path
from typing import Tuple, Optional

from tools.base import BaseTool, ToolSchema, ToolResult
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class CreateFileTool(BaseTool):
    """Tool for creating new files with content."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="create_file",
            description=(
                "Create a new file with specified content. For large files, "
                "use 'remember' tool first, then reference with content_from_memory."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working directory)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for small content).",
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
        """Orchestrate file creation."""
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

        # 3. Perform Write
        return self._perform_atomic_write(filepath, content)

    def _resolve_content(self, kwargs: dict) -> Tuple[str, Optional[ToolResult]]:
        """Determine the final content source (Scratch vs Memory vs Inline)."""
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

        return content if content is not None else "", None

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
            return "", ToolResult.internal_error(
                f"❌ Failed to read scratch file '{scratch_id}': {e}"
            )

    def _perform_atomic_write(self, filepath: str, content: str) -> ToolResult:
        """Handle the safe, atomic writing of the file."""
        full_path = self.working_dir / filepath

        try:
            if full_path.exists():
                return ToolResult.command_failed(
                    f"❌ File already exists: {filepath}", exit_code=1
                )

            full_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_to_disk(full_path, content)

            return ToolResult.success_result(f"✅ Created {filepath}")

        except PermissionError as e:
            self.logger.warning("Permission denied for %s: %s", filepath, e)
            return ToolResult.security_blocked(f"🔒 Permission denied: {filepath}")
        except OSError as e:
            self.logger.error("File system error creating %s: %s", filepath, e)
            return ToolResult.internal_error(f"❌ File system error: {e}")

    def _write_to_disk(self, full_path: Path, content: str):
        """Low-level atomic write operation."""
        temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, full_path)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                os.remove(temp_path)
            raise
