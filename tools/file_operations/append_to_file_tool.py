#!/usr/bin/env python3
import os
from pathlib import Path
from typing import Dict, Any

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
            raise ValueError("Missing 'filepath'")

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=True)

        content = kwargs.get("content")
        scratch_id = kwargs.get("content_from_scratch")

        if scratch_id:
            # Simplified logic for brevity, mirrors create_file
            scratch_path = (
                self.settings.workspace_root / ".scratch" / f"{scratch_id}.txt"
            )
            if scratch_path.exists():
                content = scratch_path.read_text(encoding="utf-8")

        if not content:
            raise ValueError("No content provided to append.")

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
