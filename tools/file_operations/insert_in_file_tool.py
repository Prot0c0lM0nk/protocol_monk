#!/usr/bin/env python3
import os
from pathlib import Path
from typing import Dict, Any

from protocol_monk.tools.base import BaseTool


class InsertInFileTool(BaseTool):
    """Tool for inserting content after a specific line in a file."""

    @property
    def name(self) -> str:
        return "insert_in_file"

    @property
    def description(self) -> str:
        return "Insert content after a specific line."

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "after_line": {
                    "type": "string",
                    "description": "Exact line content match",
                },
                "content": {"type": "string"},
            },
            "required": ["filepath", "after_line", "content"],
        }

    async def run(self, **kwargs) -> Any:
        return self._execute_sync(**kwargs)

    def _execute_sync(self, **kwargs) -> str:
        filepath = kwargs.get("filepath")
        target_line = kwargs.get("after_line")
        content = kwargs.get("content")

        if not all([filepath, target_line, content]):
            raise ValueError("Missing required params")

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=True)
        original_content = cleaned_path.read_text(encoding="utf-8")
        lines = original_content.splitlines()

        try:
            insert_idx = lines.index(target_line) + 1
        except ValueError:
            raise ValueError(f"Target line not found: '{target_line}'")

        new_lines = content.splitlines()
        updated_lines = lines[:insert_idx] + new_lines + lines[insert_idx:]

        new_text = "\n".join(updated_lines)
        if original_content.endswith("\n"):
            new_text += "\n"

        temp_path = cleaned_path.with_suffix(f"{cleaned_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            f.write(new_text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, cleaned_path)

        return f"✅ Inserted {len(new_lines)} lines after line {insert_idx} in {cleaned_path.name}"
