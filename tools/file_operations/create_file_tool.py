#!/usr/bin/env python3
import os
from pathlib import Path
from typing import Dict, Any, Optional

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.file_operations.scratch_coordination import (
    try_scratch_manager_read,
)


class CreateFileTool(BaseTool):
    """Tool for creating new files with content."""

    @property
    def name(self) -> str:
        return "create_file"

    @property
    def description(self) -> str:
        return "Create a new file with specified content."

    @property
    def requires_confirmation(self) -> bool:
        return True

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to file (relative to working dir)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write.",
                },
                "content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block.",
                },
            },
            "required": ["filepath"],
        }

    async def run(self, **kwargs) -> Any:
        return self._execute_sync(**kwargs)

    def _execute_sync(self, **kwargs) -> str:
        filepath = kwargs.get("filepath")
        if not filepath:
            raise ToolError(
                "Missing required parameter: 'filepath'",
                user_hint="Please provide a filepath for create_file.",
            )

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=False)

        # Content Resolution
        content = kwargs.get("content")
        scratch_id = kwargs.get("content_from_scratch") or kwargs.get("scratch_id")

        if content:
            # Auto-stage check logic here if needed
            pass

        if scratch_id:
            if self._looks_like_inline_content(scratch_id):
                if not content:
                    content = scratch_id
            else:
                content = self._read_scratch_file(scratch_id)

        if content is None:
            content = ""

        return self._perform_atomic_write(cleaned_path, content)

    def _read_scratch_file(self, scratch_id: str) -> str:
        content = try_scratch_manager_read(scratch_id, self.settings.workspace_root)
        if content is not None:
            return content

        # Fallback
        scratch_path = self.settings.workspace_root / ".scratch" / f"{scratch_id}.txt"
        if not scratch_path.exists():
            raise ToolError(
                f"Scratch file '{scratch_id}' not found.",
                user_hint=(
                    "Scratch content was requested, but the scratch entry was missing. "
                    "Retry with 'content' or a valid 'content_from_scratch' id."
                ),
                details={"scratch_id": scratch_id},
            )
        return scratch_path.read_text(encoding="utf-8")

    @staticmethod
    def _looks_like_inline_content(value: str) -> bool:
        """Detect when scratch slot contains raw content instead of a scratch id."""
        text = str(value).strip()
        if not text:
            return False
        return (
            "\n" in text
            or "\r" in text
            or "\t" in text
            or text.startswith("#!")
            or len(text) > 120
            or " " in text
        )

    def _perform_atomic_write(self, full_path: Path, content: str) -> str:
        if full_path.exists():
            raise ToolError(
                f"File already exists: {full_path.name}",
                user_hint=f"Cannot create '{full_path.name}' because it already exists.",
                details={"path": str(full_path)},
            )
        full_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")
        try:
            with temp_path.open("x", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, full_path)
            return f"✅ Created {full_path.name}"
        except FileExistsError:
            if temp_path.exists():
                os.remove(temp_path)
            raise ToolError(
                f"Temporary file already exists for: {full_path.name}",
                user_hint=(
                    f"Cannot create '{full_path.name}' because a temporary file already exists."
                ),
                details={"path": str(full_path), "temp_path": str(temp_path)},
            )
