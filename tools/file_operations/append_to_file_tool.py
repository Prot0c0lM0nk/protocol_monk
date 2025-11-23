#!/usr/bin/env python3
"""
Append to File Tool - Tool for appending content to the end of a file
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from agent import exceptions
from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class AppendToFileTool(BaseTool):
    """Tool for appending content to the end of a file without modifying existing content."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="append_to_file",
            description="[USE THIS FOR ADDING NEW CONTENT] Add content to the END of a file without modifying existing content. Perfect for adding new functions, classes, or configuration. For large content, use 'remember' tool first.",
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to append to (relative to working directory)"
                },
                "content": {
                    "type": "string",
                    "description": "Content to add to the end of the file (for small content). For large content, use content_from_memory instead."
                },
                "content_from_memory": {
                    "type": "string",
                    "description": "Memory key containing the content to append (use 'remember' tool first to store large content)"
                },
                "content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block (system auto-stages code blocks from conversational output)"
                }
            },
            required_params=["filepath"]
        )

    def execute(self, **kwargs) -> ToolResult:
        """Append content to the end of a file."""
        filepath = kwargs.get("filepath")
        content = kwargs.get("content")
        content_from_memory = kwargs.get("content_from_memory")
        content_from_scratch = kwargs.get("content_from_scratch")

        # Validate required parameters
        if not filepath:
            return ToolResult.invalid_params("❌ Missing required parameter: 'filepath'", missing_params=['filepath'])

        # AUTO-STAGING: If inline content is too large, auto-stage it
        if content:
            staged_id = auto_stage_large_content(content, self.working_dir)
            if staged_id:
                content_from_scratch = staged_id
                content = None

        # Get content from scratch, memory, or inline parameter
        if content_from_scratch:
            scratch_path = self.working_dir / ".scratch" / f"{content_from_scratch}.txt"
            if not scratch_path.exists():
                return ToolResult(ExecutionStatus.INVALID_PARAMS, f"❌ Scratch file '{content_from_scratch}' not found.")
            try:
                content = scratch_path.read_text(encoding='utf-8')
            except Exception as e:
                return ToolResult(ExecutionStatus.INTERNAL_ERROR, f"❌ Failed to read scratch file: {e}")
        elif content_from_memory:
            return ToolResult.internal_error("❌ The 'content_from_memory' feature is not supported in this version.")
        elif not content:
            return ToolResult.invalid_params(
                "❌ Must provide 'content', 'content_from_memory', or 'content_from_scratch' parameter",
                missing_params=['content', 'content_from_memory', 'content_from_scratch']
            )

        # Security validation
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(f"🔒 File path blocked due to security policy: {filepath}", reason="Unsafe file path")

        full_path = self.working_dir / filepath

        try:
            # Read existing content
            existing_content = full_path.read_text(encoding='utf-8')

            # Determine if we need to add a newline separator
            separator = "\n"
            if existing_content and not existing_content.endswith('\n'):
                separator = "\n\n"  # Extra space if file doesn't end with newline
            elif not existing_content:
                separator = ""  # No separator for empty files

            # Create new content
            new_content = existing_content + separator + content

            # Atomic write
            temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")

            with temp_path.open('w', encoding='utf-8') as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())

            os.replace(temp_path, full_path)

            # Show what was added
            added_lines = content.splitlines()
            line_count = len(added_lines)

            result_message = f"✅ Appended {line_count} line(s) to {filepath}\n"
            result_message += f"📝 Added content:\n{'-' * 40}\n{content}\n{'-' * 40}"

            return ToolResult.success_result(
                result_message,
                data={
                    "filepath": filepath,
                    "lines_added": line_count,
                    "added_content": content
                }
            )

        except FileNotFoundError:
            return ToolResult.command_failed(f"❌ File not found: {filepath}", exit_code=1)
        except PermissionError as e:
            self.logger.warning(f"Permission denied for {filepath}: {e}", exc_info=True)
            return ToolResult.security_blocked(f"🔒 Permission denied: Cannot write to {filepath}.", reason=str(e))
        except UnicodeDecodeError as e:
            return ToolResult.internal_error(f"❌ Encoding error: Cannot read {filepath} as 'utf-8'. It may be a binary file. Error: {e}")
        except UnicodeEncodeError as e:
            return ToolResult.internal_error(f"❌ Encoding error: Cannot write new content to {filepath} as 'utf-8'. Error: {e}")
        except (IOError, OSError) as e:
            self.logger.error(f"File system error appending to {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error appending to {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")
