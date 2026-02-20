#!/usr/bin/env python3
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool


class ReadFileTool(BaseTool):
    """Tool for reading specific lines from a file."""

    MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024  # 1 MB limit

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read and display file contents, with optional line range."

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
                    "description": "Starting line number (1-based, optional).",
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number (1-based, optional).",
                },
            },
            "required": ["filepath"],
        }

    async def run(self, **kwargs) -> Any:
        # Note: BaseTool.run is async, so we just run the sync logic here
        # In a strict async system, file I/O should be wrapped in run_in_executor
        # But for this phase, direct execution is acceptable as per prototype
        return self._execute_sync(**kwargs)

    def _execute_sync(self, **kwargs) -> str:
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
        return self._format_output(
            str(cleaned_path), selected_lines, actual_start, actual_end
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
        start_idx = (start - 1) if start else 0
        end_idx = end if end else total_lines

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

    def _format_output(
        self, filepath: str, lines: List[str], start: int, end: int
    ) -> str:
        numbered_content = "\n".join(
            f"{i+start:3}│ {line}" for i, line in enumerate(lines)
        )
        return (
            f"📄 File {filepath} (lines {start}-{end}):\n"
            f"{'─' * 60}\n{numbered_content}\n{'─' * 60}"
        )
