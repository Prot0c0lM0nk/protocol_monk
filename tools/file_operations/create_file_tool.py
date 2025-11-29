#!/usr/bin/env python3
"""
Create File Tool - Tool for creating new files with content
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from agent import exceptions
from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
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
            description="Create a new file with specified content. For large files, use 'remember' tool first, then reference with content_from_memory.",
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to create (relative to working directory)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file (for small content). For large files, use content_from_memory instead.",
                },
                "content_from_memory": {
                    "type": "string",
                    "description": "Memory key containing the file content (use 'remember' tool first to store large content)",
                },
                "content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block (system auto-stages code blocks from conversational output)",
                },
            },
            required_params=["filepath"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """Create a new file with content."""
        filepath = kwargs.get("filepath")
        content = kwargs.get("content")
        content_from_memory = kwargs.get("content_from_memory")
        content_from_scratch = kwargs.get("content_from_scratch")

        # Validate required parameters
        if not filepath:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'filepath'", missing_params=["filepath"]
            )

        # AUTO-STAGING: If inline content is too large, auto-stage it
        if content:
            staged_id = auto_stage_large_content(content, self.working_dir)
            if staged_id:
                content_from_scratch = staged_id
                content = None

        # Get content from scratch, memory, or inline parameter (priority order)
        if content_from_scratch:
            # Read from scratch file
            scratch_path = self.working_dir / ".scratch" / f"{content_from_scratch}.txt"
            if not scratch_path.exists():
                return ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Scratch file '{content_from_scratch}' not found. Available scratch files: {list((self.working_dir / '.scratch').glob('*.txt'))}",
                )
            try:
                content = scratch_path.read_text(encoding="utf-8")
            except Exception as e:
                return ToolResult(
                    ExecutionStatus.INTERNAL_ERROR,
                    f"❌ Failed to read scratch file '{content_from_scratch}': {e}",
                )
        elif content_from_memory:
            return ToolResult.internal_error(
                "❌ The 'content_from_memory' feature is not supported in this version."
            )
        elif content is None:
            # Default to creating an empty file if no content is provided
            content = ""

        # Security validation for file path
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(
                f"🔒 File path blocked due to security policy: {filepath}",
                reason="Unsafe file path",
            )

        full_path = self.working_dir / filepath

        try:
            # Create parent directories if they don't exist
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if full_path.exists():
                return ToolResult.command_failed(
                    f"❌ File already exists: {filepath}", exit_code=1
                )

            # Atomic write: write to temp file, then replace
            temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")

            # Write and sync in one operation
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace operation (already durable after fsync above)
            os.replace(temp_path, full_path)

            # Show the created file content
            self._show_file_content(filepath, content, "Created")

            return ToolResult.success_result(f"✅ Created {filepath}")

        except FileExistsError:
            return ToolResult.command_failed(
                f"❌ File already exists: {filepath}", exit_code=1
            )
        except PermissionError as e:
            self.logger.warning(f"Permission denied for {filepath}: {e}", exc_info=True)
            return ToolResult.security_blocked(
                f"🔒 Permission denied: Cannot create {filepath}.", reason=str(e)
            )
        except UnicodeEncodeError as e:
            return ToolResult.internal_error(
                f"❌ Encoding error: Cannot write content to {filepath} as 'utf-8'. Error: {e}"
            )
        except (IOError, OSError) as e:
            self.logger.error(
                f"File system error creating file {filepath}: {e}", exc_info=True
            )
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:
            self.logger.error(
                f"Unexpected error creating file {filepath}: {e}", exc_info=True
            )
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")

    def _show_file_content(self, filepath: str, content: str, action: str):
        """Helper to format file content for display."""
        # This is a placeholder. In a real CLI, you might use a pager or truncate.
        header = f"📄 {action} file: {filepath}"
        # self.console.print(f"\n{header}\n{'─' * len(header)}\n{content}\n{'─' * len(header)}\n")
