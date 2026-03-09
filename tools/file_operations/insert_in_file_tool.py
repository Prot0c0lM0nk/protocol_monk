#!/usr/bin/env python3
import os
from typing import Dict, Any

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.output_contract import build_tool_output, count_lines


class InsertInFileTool(BaseTool):
    """Tool for inserting content after a specific line in a file."""

    @property
    def name(self) -> str:
        return "insert_in_file"

    @property
    def description(self) -> str:
        return "Insert content after a specific line."

    @property
    def requires_confirmation(self) -> bool:
        return True

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
            raise ToolError(
                "Missing required params",
                user_hint="filepath, after_line, and content are required.",
            )

        cleaned_path = self.path_validator.validate_path(filepath, must_exist=True)
        original_content = cleaned_path.read_text(encoding="utf-8")
        lines = original_content.splitlines()

        try:
            insert_idx = lines.index(target_line) + 1
        except ValueError:
            raise ToolError(
                f"Target line not found: '{target_line}'",
                user_hint="The specified anchor line was not found in the file.",
                details={"target_line": target_line, "path": str(cleaned_path)},
            )

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

        return build_tool_output(
            result_type="file_insert",
            summary=(
                f"Inserted {len(new_lines)} line(s) into {cleaned_path.name} "
                f"after line {insert_idx}."
            ),
            data={
                "operation": "insert_in_file",
                "path": str(cleaned_path),
                "anchor_text": target_line,
                "inserted_after_line": insert_idx,
                "inserted_line_count": len(new_lines),
                "inserted_char_count": len(content),
                "inserted_content_line_count": count_lines(content),
                "previous_total_lines": len(lines),
                "new_total_lines": len(updated_lines),
            },
            pagination=None,
        )
