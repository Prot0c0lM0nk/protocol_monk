#!/usr/bin/env python3
import os
from pathlib import Path
from typing import Dict, Any, Optional

from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.file_operations.auto_stage_large_content import (
    auto_stage_large_content,
)
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
            raise ValueError("Missing required parameter: 'filepath'")

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=False)

        # Content Resolution
        content = kwargs.get("content")
        scratch_id = kwargs.get("content_from_scratch")

        if content:
            # Auto-stage check logic here if needed
            pass

        if scratch_id:
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
            raise ValueError(f"Scratch file '{scratch_id}' not found.")
        return scratch_path.read_text(encoding="utf-8")

    def _perform_atomic_write(self, full_path: Path, content: str) -> str:
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
            raise ValueError(f"File already exists: {full_path.name}")
