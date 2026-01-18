#!/usr/bin/env python3
import os
from pathlib import Path
from typing import Dict, Any

from protocol_monk.tools.base import BaseTool


class DeleteLinesTool(BaseTool):
    @property
    def name(self) -> str:
        return "delete_lines"

    @property
    def description(self) -> str:
        return "Delete specific line numbers."

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "line_start": {"type": "integer"},
                "line_end": {"type": "integer"},
            },
            "required": ["filepath", "line_start", "line_end"],
        }

    async def run(self, **kwargs) -> Any:
        filepath = kwargs.get("filepath")
        start = kwargs.get("line_start")
        end = kwargs.get("line_end")

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=True)
        content = cleaned_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        start_idx = start - 1

        if start_idx < 0 or end > len(lines):
            raise ValueError("Invalid range")

        updated_lines = lines[:start_idx] + lines[end:]
        final_text = "\n".join(updated_lines)
        if content.endswith("\n"):
            final_text += "\n"

        temp_path = cleaned_path.with_suffix(f"{cleaned_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            f.write(final_text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, cleaned_path)

        return f"✅ Deleted lines {start}-{end} from {cleaned_path.name}"
