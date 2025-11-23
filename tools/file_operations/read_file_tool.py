#!/usr/bin/env python3
"""
Read File Tool - Tool for reading specific lines from a file
"""

import logging
from pathlib import Path
from typing import Dict, Any

from agent import exceptions
from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus


class ReadFileTool(BaseTool):
    """Tool for reading specific lines from a file, preferring cached content."""

    MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024  # 1 MB limit

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_file",
            description="Read and display file contents, with optional line range. Uses cached content when available.",
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to show"
                },
                "line_start": {
                    "type": "integer",
                    "description": "Starting line number (1-based, optional). If omitted, shows entire file."
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number (1-based, optional). If omitted, shows to end of file."
                }
            },
            required_params=["filepath"]
        )

    def execute(self, **kwargs) -> ToolResult:
        """Show specific lines from a file, preferring cached content."""
        filepath = kwargs.get("filepath")
        line_start = kwargs.get("line_start")
        line_end = kwargs.get("line_end")

        # Validate required parameters
        if not filepath:
            return ToolResult.invalid_params("❌ Missing required parameter: 'filepath'", missing_params=['filepath'])

        # Security validation for file path (read_only=True allows reading outside working_dir)
        if not self._is_safe_file_path(filepath, read_only=True):
            return ToolResult.security_blocked(f"🔒 File path blocked due to security policy: {filepath}", reason="Unsafe file path")

        try:
            full_path = self.working_dir / filepath

            # Check file size before reading
            file_size = full_path.stat().st_size
            if file_size > self.MAX_FILE_SIZE_BYTES:
                return ToolResult.command_failed(
                    f"❌ File is too large to read ({file_size / 1024:.2f} KB). Maximum size is {self.MAX_FILE_SIZE_BYTES / 1024:.2f} KB.",
                    exit_code=1
                )
            content = full_path.read_text(encoding='utf-8')

            lines = content.splitlines()

            # Default to showing all lines if no range specified
            start_idx = (line_start - 1) if line_start else 0
            end_idx = line_end if line_end else len(lines)

            # Validate range
            start_idx = max(0, start_idx)
            end_idx = min(len(lines), end_idx)

            if start_idx >= len(lines):
                return ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Start line {line_start} exceeds file length ({len(lines)} lines)"
                )

            # Get the specified lines
            selected_lines = lines[start_idx:end_idx]
            numbered_content = "\n".join(f"{i+start_idx+1:3}│ {line}" for i, line in enumerate(selected_lines))

            # Return formatted content - let main agent handle display
            formatted_output = f"📄 File {filepath} (lines {start_idx+1}-{end_idx}):\n{'─' * 60}\n{numbered_content}\n{'─' * 60}"

            return ToolResult.success_result(
                formatted_output,
                data={"filepath": filepath, "line_start": start_idx+1, "line_end": end_idx, "content": "\n".join(selected_lines)}
            )

        except FileNotFoundError:
            return ToolResult.command_failed(f"❌ File not found: {filepath}", exit_code=1)
        except PermissionError as e:
            self.logger.warning(f"Permission denied for {filepath}: {e}", exc_info=True)
            return ToolResult.security_blocked(f"🔒 Permission denied: Cannot read {filepath}.", reason=str(e))
        except UnicodeDecodeError as e:
            return ToolResult.internal_error(f"❌ Encoding error: Cannot read {filepath} as 'utf-8'. It may be a binary file. Error: {e}")
        except (IOError, OSError) as e:
            self.logger.error(f"File system error reading {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error reading {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")
