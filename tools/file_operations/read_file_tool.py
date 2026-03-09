#!/usr/bin/env python3
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.output_contract import (
    build_line_pagination,
    build_tool_output,
    summarize_line_range,
)


class ReadFileTool(BaseTool):
    """Tool for reading specific lines from a file."""

    MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024  # 1 MB limit
    DEFAULT_PAGE_LINES: int = 200

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read file contents as structured line records. "
            "Defaults to the first 200 lines unless a line range is provided."
        )

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to show",
                },
                "line_start": {
                    "type": "integer",
                    "description": (
                        "Starting line number (1-based, optional). "
                        "If provided without line_end, returns up to 200 lines."
                    ),
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number (1-based, optional, inclusive).",
                },
            },
            "required": ["filepath"],
        }

    async def run(self, **kwargs) -> Any:
        # Note: BaseTool.run is async, so we just run the sync logic here
        # In a strict async system, file I/O should be wrapped in run_in_executor
        # But for this phase, direct execution is acceptable as per prototype
        return self._execute_sync(**kwargs)

    def _execute_sync(self, **kwargs) -> Dict[str, Any]:
        filepath = kwargs.get("filepath")
        if not filepath:
            raise ToolError(
                "Missing required parameter: 'filepath'",
                user_hint="Please provide a filepath for read_file.",
            )

        # Validator is initialized in BaseTool
        cleaned_path = self.path_validator.validate_path(filepath, must_exist=False)

        # 1. Read File
        lines = self._validate_and_read(cleaned_path)

        # 2. Extract Range
        start = kwargs.get("line_start")
        end = kwargs.get("line_end")
        selected_lines, actual_start, actual_end = self._extract_range(
            lines, start, end
        )

        # 3. Format Output
        return self._build_output(
            str(cleaned_path),
            total_lines=len(lines),
            lines=selected_lines,
            requested_start=start,
            requested_end=end,
            actual_start=actual_start,
            actual_end=actual_end,
        )

    def _validate_and_read(self, full_path: Path) -> List[str]:
        try:
            file_stat = full_path.stat()
            if file_stat.st_size > self.MAX_FILE_SIZE_BYTES:
                size_kb = self.MAX_FILE_SIZE_BYTES / 1024
                raise ToolError(
                    f"File too large (> {size_kb:.2f} KB).",
                    user_hint="File is too large to read in one call.",
                    details={
                        "path": str(full_path),
                        "max_size_bytes": self.MAX_FILE_SIZE_BYTES,
                        "actual_size_bytes": file_stat.st_size,
                    },
                )

            content = full_path.read_text(encoding="utf-8")
            return content.splitlines()

        except FileNotFoundError:
            raise ToolError(
                f"File not found: {full_path.name}",
                user_hint=f"The file '{full_path.name}' does not exist.",
                details={"path": str(full_path)},
            )
        except PermissionError:
            raise ToolError(
                f"Permission denied: {full_path.name}",
                user_hint=f"No permission to read '{full_path.name}'.",
                details={"path": str(full_path)},
            )
        except UnicodeDecodeError:
            raise ToolError(
                "Encoding error. File may be binary.",
                user_hint="File is not UTF-8 text (possibly binary).",
                details={"path": str(full_path)},
            )

    def _extract_range(
        self, lines: List[str], start: Optional[int], end: Optional[int]
    ) -> Tuple[List[str], int, int]:
        total_lines = len(lines)
        if total_lines == 0:
            return [], 1, 0

        start_idx = (start - 1) if start else 0
        if end:
            end_idx = end
        elif start:
            end_idx = min(total_lines, start_idx + self.DEFAULT_PAGE_LINES)
        else:
            end_idx = min(total_lines, self.DEFAULT_PAGE_LINES)

        start_idx = max(0, start_idx)
        end_idx = min(total_lines, end_idx)

        if start and start_idx >= total_lines:
            raise ToolError(
                f"Start line {start} exceeds length ({total_lines})",
                user_hint=(
                    f"Requested start line {start} is beyond file length {total_lines}."
                ),
                details={"line_start": start, "total_lines": total_lines},
            )

        return lines[start_idx:end_idx], start_idx + 1, end_idx

    def _build_output(
        self,
        filepath: str,
        *,
        total_lines: int,
        lines: List[str],
        requested_start: Optional[int],
        requested_end: Optional[int],
        actual_start: int,
        actual_end: int,
    ) -> Dict[str, Any]:
        line_records = [
            {"line_number": actual_start + index, "text": line}
            for index, line in enumerate(lines)
        ]
        returned_count = len(line_records)
        page_size = returned_count or self.DEFAULT_PAGE_LINES
        pagination = build_line_pagination(
            total_lines=total_lines,
            returned_start=actual_start,
            returned_end=actual_end,
            page_size=page_size,
        )
        range_summary = (
            summarize_line_range(actual_start, actual_end)
            if actual_end >= actual_start
            else "no lines"
        )

        return build_tool_output(
            result_type="file_read",
            summary=f"Read {range_summary} from {filepath}.",
            data={
                "path": filepath,
                "requested_range": {
                    "line_start": requested_start,
                    "line_end": requested_end,
                },
                "actual_range": {
                    "line_start": actual_start,
                    "line_end": actual_end,
                },
                "total_lines": total_lines,
                "returned_line_count": returned_count,
                "lines": line_records,
            },
            pagination=pagination,
        )
