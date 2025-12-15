#!/usr/bin/env python3
"""
Create File Tool - Tool for creating new files with content.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple
from tools.path_validator import PathValidator
from tools.file_operations.auto_stage_large_content import auto_stage_large_content
from tools.file_operations.scratch_coordination import try_scratch_manager_read
from tools.base import BaseTool, ToolResult, ToolSchema
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class CreateFileTool(BaseTool):
    """Tool for creating new files with content."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)
        self.path_validator = PathValidator(working_dir)

    @property
    def schema(self) -> ToolSchema:
        """
        Return the tool schema.

        Returns:
            ToolSchema: The definition of the tool's interface.
        """
        return ToolSchema(
            name="create_file",
            description=(
                "Create a new file with specified content. For large files, "
                "use 'remember' tool first, then 'content_from_memory'."
            ),
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to file (relative to working dir)",
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
        """
        Orchestrate file creation.

        Args:
            **kwargs: Arbitrary keyword arguments (filepath, content, etc).

        Returns:
            ToolResult: The result of the file creation operation.
        """
        filepath = kwargs.get("filepath")
        if not filepath:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'filepath'", missing_params=["filepath"]
            )

        # Use centralized path validator
        cleaned_path, error = self.path_validator.validate_and_clean_path(filepath)
        if error:
            return ToolResult.security_blocked(f"Invalid path: {error}")

        filepath = cleaned_path

        # 1. Resolve Content
        content, error = self._resolve_content(kwargs)
        if error:
            return error

        # Path validation completed, proceed with operation

        # 3. Perform Write
        return self._perform_atomic_write(filepath, content)

    def _resolve_content(self, kwargs: dict) -> Tuple[str, Optional[ToolResult]]:
        """
        Determine the final content source.

        Args:
            kwargs: Dictionary of arguments passed to execute.

        Returns:
            Tuple[str, Optional[ToolResult]]: The resolved content and an
            optional error result.
        """
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
                "❌ The 'content_from_memory' feature is not supported."
            )

        return content if content is not None else "", None

    def _read_scratch_file(self, scratch_id: str) -> Tuple[str, Optional[ToolResult]]:
        """
        Read content from a staged scratch file.

        Args:
            scratch_id: The ID of the scratch file to read.

        Returns:
            Tuple[str, Optional[ToolResult]]: The content of the file and
            an optional error result.
        """
        # Try ScratchManager first
        content = try_scratch_manager_read(scratch_id, self.working_dir)
        if content is not None:
            return content, None

        # Fallback to existing hardcoded logic
        scratch_path = self.working_dir / ".scratch" / f"{scratch_id}.txt"

        if not scratch_path.exists():
            return "", ToolResult.invalid_params(
                f"❌ Scratch file '{scratch_id}' not found.",
                missing_params=["content_from_scratch"],
            )

        try:
            return scratch_path.read_text(encoding="utf-8"), None
        except OSError as e:
            return "", ToolResult.internal_error(
                f"❌ Failed to read scratch file '{scratch_id}': {e}"
            )

    def _perform_atomic_write(self, filepath: str, content: str) -> ToolResult:
        """
        Handle the safe, atomic writing of the file.

        Args:
            filepath: The relative path to the file.
            content: The content to write.

        Returns:
            ToolResult: The result of the write operation.
        """
        full_path = self.working_dir / filepath

        try:
            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Attempt atomic write with exclusive creation
            temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")
            try:
                with temp_path.open("x", encoding="utf-8") as f:  # "x" mode ensures exclusive creation
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, full_path)
                
                return ToolResult.success_result(f"✅ Created {filepath}")
            except FileExistsError:
                # Clean up temp file if it exists
                if temp_path.exists():
                    os.remove(temp_path)
                return ToolResult.command_failed(
                    f"❌ File already exists: {filepath}", exit_code=1
                )
                
        except PermissionError as e:
            self.logger.warning("Permission denied for %s: %s", filepath, e)
            return ToolResult.security_blocked(f"🔒 Permission denied: {filepath}")
        except OSError as e:
            self.logger.error("File system error creating %s: %s", filepath, e)
            return ToolResult.internal_error(f"❌ File system error: {e}")
    def _write_to_disk(self, full_path: Path, content: str):
        """
        Low-level atomic write operation.

        Args:
            full_path: The absolute path to write to.
            content: The content to write.

        Raises:
            Exception: If the write fails, cleanup is attempted,
                then the error is re-raised.
        """
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
