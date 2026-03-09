#!/usr/bin/env python3
import os
from typing import Dict, Any

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.output_contract import build_tool_output, count_lines


class ReplaceLinesTool(BaseTool):
    @property
    def name(self) -> str:
        return "replace_lines"

    @property
    def description(self) -> str:
        return "Delete lines from start to end and insert new content."

    @property
    def requires_confirmation(self) -> bool:
        return True

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "line_start": {"type": "integer"},
                "line_end": {"type": "integer"},
                "new_content": {"type": "string"},
            },
            "required": ["filepath", "line_start", "line_end", "new_content"],
        }

    async def run(self, **kwargs) -> Any:
        filepath = kwargs.get("filepath")
        start = kwargs.get("line_start")
        end = kwargs.get("line_end")
        new_content = kwargs.get("new_content")

        if filepath is None or start is None or end is None or new_content is None:
            raise ToolError(
                "Missing required params",
                user_hint="filepath, line_start, line_end, and new_content are required.",
            )

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=True)
        content = cleaned_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        start_idx = start - 1

        if start_idx < 0 or end > len(lines) or start_idx >= end:
            raise ToolError(
                f"Invalid range: {start}-{end}",
                user_hint=f"Line range {start}-{end} is invalid for this file.",
                details={
                    "line_start": start,
                    "line_end": end,
                    "total_lines": len(lines),
                },
            )

        new_lines_list = new_content.splitlines()
        updated_lines = lines[:start_idx] + new_lines_list + lines[end:]

        final_text = "\n".join(updated_lines)
        if content.endswith("\n"):
            final_text += "\n"

        temp_path = cleaned_path.with_suffix(f"{cleaned_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            f.write(final_text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, cleaned_path)

        return build_tool_output(
            result_type="file_replace_lines",
            summary=f"Replaced lines {start}-{end} in {cleaned_path.name}.",
            data={
                "operation": "replace_lines",
                "path": str(cleaned_path),
                "line_start": start,
                "line_end": end,
                "replaced_line_count": end - start + 1,
                "inserted_line_count": len(new_lines_list),
                "new_content_char_count": len(new_content),
                "new_content_line_count": count_lines(new_content),
                "previous_total_lines": len(lines),
                "new_total_lines": len(updated_lines),
            },
            pagination=None,
        )
