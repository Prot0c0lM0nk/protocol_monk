#!/usr/bin/env python3
"""
Replace Lines Tool - Replace specific line numbers in a file.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

from tools.base import BaseTool, ExecutionStatus, ToolResult, ToolSchema
from tools.path_validator import PathValidator
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class ReplaceLinesTool(BaseTool):
    """Tool for replacing specific line numbers in a file."""

    def __init__(self, working_dir: Path, context_manager=None):
        super().__init__(working_dir)
        self.context_manager = context_manager
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
            name="replace_lines",
            description=(
                "[DANGER] Delete lines from start to end (inclusive) and "
                "insert new content."
            ),
            parameters={
                "filepath": {"type": "string", "description": "Path to file"},
                "line_start": {
                    "type": "integer",
                    "description": "Start line (1-based)",
                },
                "line_end": {
                    "type": "integer",
                    "description": "End line (1-based, inclusive)",
                },
                "new_content": {"type": "string", "description": "New content"},
                "new_content_from_memory": {
                    "type": "string",
                    "description": "Memory key",
                },
                "new_content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID",
                },
            },
            required_params=["filepath", "line_start", "line_end"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """
        Orchestrate the replacement.

        Args:
            **kwargs: Arbitrary keyword arguments.

        Returns:
            ToolResult: The result of the replacement operation.
        """
        # 1. Validate & Resolve Content
        filepath, start, end, content, error = self._validate_inputs(kwargs)
        if error:
            return error

        # 2. Read & Apply Logic
        full_path = self.working_dir / filepath
        # pylint: disable=unpacking-non-sequence
        new_text, old_lines, logic_error = self._apply_replacement(
            full_path, start, end, content
        )
        if logic_error:
            return logic_error

        # 3. Write
        write_error = self._perform_atomic_write(full_path, new_text)
        if write_error:
            return write_error

        # 4. Success Result
        return self._format_success(
            filepath, (start, end), old_lines, content.splitlines()
        )

    def _validate_inputs(
        self, kwargs: dict
    ) -> Tuple[
        Optional[str], Optional[int], Optional[int], Optional[str], Optional[ToolResult]
    ]:
        """
        Validate parameters and resolve content source.

        Args:
            kwargs: Dictionary of inputs.

        Returns:
            Tuple: (filepath, start, end, content, error_result).
        """
        filepath = kwargs.get("filepath")
        start = kwargs.get("line_start")
        end = kwargs.get("line_end")

        if not filepath or not start or not end:
            return (
                None,
                None,
                None,
                None,
                ToolResult.invalid_params(
                    "❌ Missing required params.",
                    missing_params=["filepath", "line_start", "line_end"],
                ),
            )

        # Use centralized path validator
        cleaned_path, error = self.path_validator.validate_and_clean_path(filepath)
        if error:
            return (
                None,
                None,
                None,
                None,
                ToolResult.security_blocked(f"Invalid path: {error}"),
            )

        filepath = cleaned_path

        content, error = self._resolve_content(**kwargs)
        if error:
            return None, None, None, None, error

        return filepath, start, end, content, None

    def _resolve_content(self, **kwargs) -> Tuple[Optional[str], Optional[ToolResult]]:
        """
        Resolve content from scratch, memory, or inline.

        Args:
            **kwargs: Arguments containing content identifiers.

        Returns:
            Tuple: (Resolved content string, Error result).
        """
        content = kwargs.get("new_content")
        memory_key = kwargs.get("new_content_from_memory")
        scratch_id = kwargs.get("new_content_from_scratch")

        if content:
            staged_id = auto_stage_large_content(content, self.working_dir)
            if staged_id:
                scratch_id = staged_id
                content = None

        if scratch_id:
            return self._read_scratch(scratch_id)

        if memory_key:
            return self._read_memory(memory_key)

        if content is not None:
            return content, None

        return None, ToolResult.invalid_params(
            "❌ Must provide content via inline, memory, or scratch.",
            missing_params=["new_content"],
        )

    def _read_scratch(
        self, scratch_id: str
    ) -> Tuple[Optional[str], Optional[ToolResult]]:
        path = self.working_dir / ".scratch" / f"{scratch_id}.txt"
        if not path.exists():
            return None, ToolResult.invalid_params(
                f"❌ Scratch file '{scratch_id}' not found."
            )
        try:
            return path.read_text(encoding="utf-8"), None
        except OSError as e:
            return None, ToolResult.internal_error(f"❌ Error reading scratch: {e}")

    def _read_memory(self, key: str) -> Tuple[Optional[str], Optional[ToolResult]]:
        if not self.context_manager:
            return None, ToolResult.internal_error("❌ Memory system unavailable.")
        if key not in self.context_manager.working_memory:
            return None, ToolResult.invalid_params(f"❌ Memory key '{key}' not found.")
        return self.context_manager.working_memory[key], None

    def _apply_replacement(
        self, full_path: Path, start: int, end: int, new_content: str
    ) -> Tuple[str, List[str], Optional[ToolResult]]:
        """
        Read file, splice lines, and prepare new content.

        Args:
            full_path: Absolute path to the file.
            start: Start line number.
            end: End line number.
            new_content: The new text to insert.

        Returns:
            Tuple: (New full text, List of old lines, Error result).
        """
        try:
            content = full_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (
                "",
                [],
                ToolResult.command_failed(
                    f"❌ File not found: {full_path.name}", exit_code=1
                ),
            )
        except OSError as e:
            return "", [], ToolResult.internal_error(f"❌ Error reading file: {e}")

        lines = content.splitlines()
        start_idx = start - 1
        end_idx = end

        if start_idx < 0 or end_idx > len(lines) or start_idx >= end_idx:
            return (
                "",
                [],
                ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Invalid range: {start}-{end} " f"(File: {len(lines)} lines)",
                ),
            )

        old_lines = lines[start_idx:end_idx]
        new_lines_list = new_content.splitlines()

        updated_lines = lines[:start_idx] + new_lines_list + lines[end_idx:]
        final_content = "\n".join(updated_lines)

        if content.endswith("\n"):
            final_content += "\n"

        return final_content, old_lines, None

    def _perform_atomic_write(self, path: Path, content: str) -> Optional[ToolResult]:
        """
        Perform robust atomic write.

        Args:
            path: Absolute path to write.
            content: Content to write.

        Returns:
            Optional[ToolResult]: None if success, Error if failed.
        """
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
            return None
        except OSError as e:
            self.logger.error("Error writing %s: %s", path, e)
            return ToolResult.internal_error(f"❌ File system error: {e}")

    def _format_success(
        self, filepath: str, line_range: Tuple[int, int], old: List[str], new: List[str]
    ) -> ToolResult:
        """
        Create success result with diff.

        Args:
            filepath: Path to the file.
            line_range: Tuple of (start_line, end_line).
            old: List of lines removed.
            new: List of lines added.

        Returns:
            ToolResult: Success result with formatted output.
        """
        start, end = line_range
        msg_lines = [
            f"✅ Replaced lines {start}-{end} in {filepath}",
            f"📝 Changes ({len(old)} → {len(new)} lines):",
            "─" * 50,
        ]
        for i, line in enumerate(old):
            msg_lines.append(f"-{start + i:3}│ {line}")
        for i, line in enumerate(new):
            msg_lines.append(f"+{start + i:3}│ {line}")
        msg_lines.append("─" * 50)

        return ToolResult.success_result("\n".join(msg_lines))
