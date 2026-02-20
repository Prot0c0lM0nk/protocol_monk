#!/usr/bin/env python3
import os
from pathlib import Path
from typing import Dict, Any

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.file_operations.scratch_coordination import (
    try_scratch_manager_read,
)


class AppendToFileTool(BaseTool):
    """Tool for appending content to the end of a file."""

    @property
    def name(self) -> str:
        return "append_to_file"

    @property
    def description(self) -> str:
        return "Add content to the END of a file."

    @property
    def requires_confirmation(self) -> bool:
        return True

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "content": {"type": "string"},
                "content_from_scratch": {"type": "string"},
            },
            "required": ["filepath"],
        }

    async def run(self, **kwargs) -> Any:
        return self._execute_sync(**kwargs)

    def _execute_sync(self, **kwargs) -> str:
        filepath = kwargs.get("filepath")
        if not filepath:
            raise ToolError(
                "Missing 'filepath'",
                user_hint="Please provide a filepath for append_to_file.",
            )

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=True)

        content = kwargs.get("content")
        scratch_id = kwargs.get("content_from_scratch") or kwargs.get("scratch_id")

        if scratch_id:
            if self._looks_like_inline_content(scratch_id):
                if not content:
                    content = scratch_id
            else:
                content = self._read_scratch_file(scratch_id)

        if not content:
            raise ToolError(
                "No content provided to append.",
                user_hint="Provide 'content' or a valid 'content_from_scratch' value.",
            )

        existing = cleaned_path.read_text(encoding="utf-8")
        separator = "\n" if existing and not existing.endswith("\n") else ""
        if not existing:
            separator = ""

        new_content = existing + separator + content

        # Atomic Write
        temp_path = cleaned_path.with_suffix(f"{cleaned_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            f.write(new_content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, cleaned_path)

        return f"✅ Appended to {cleaned_path.name}"

    def _read_scratch_file(self, scratch_id: str) -> str:
        content = try_scratch_manager_read(scratch_id, self.settings.workspace_root)
        if content is not None:
            return content

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
