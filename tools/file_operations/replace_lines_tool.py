#!/usr/bin/env python3
"""
Replace Lines Tool - Replace specific line numbers in a file.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from agent import exceptions
from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class ReplaceLinesTool(BaseTool):
    """Tool for replacing specific line numbers in a file."""

    def __init__(self, working_dir: Path, context_manager=None):
        super().__init__(working_dir)
        self.context_manager = context_manager
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="replace_lines",
            description="[DANGER] Deletes all lines from 'line_start' to 'line_end' (inclusive) and inserts 'new_content' in their place. Use 'read_file' to get exact line numbers first. This tool is for replacing code blocks.",
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working directory)"
                },
                "line_start": {
                    "type": "integer",
                    "description": "Starting line number to replace (1-based)"
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number to replace (1-based, inclusive)"
                },
                "new_content": {
                    "type": "string",
                    "description": "New content to replace the specified lines (for small content). For large content, use new_content_from_memory instead."
                },
                "new_content_from_memory": {
                    "type": "string",
                    "description": "Memory key containing the replacement content (use 'remember' tool first to store large content)"
                },
                "new_content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block (system auto-stages code blocks from conversational output)"
                }
            },
            required_params=["filepath", "line_start", "line_end"]
        )

    
    def execute(self, **kwargs) -> ToolResult:
        """Replace specific line range in a file."""
        filepath = kwargs.get("filepath")
        line_start = kwargs.get("line_start")
        line_end = kwargs.get("line_end")
        new_content = kwargs.get("new_content")
        new_content_from_memory = kwargs.get("new_content_from_memory")
        new_content_from_scratch = kwargs.get("new_content_from_scratch")

        # Validate required parameters
        if not filepath:
            return ToolResult.invalid_params("❌ Missing required parameter: 'filepath'", missing_params=['filepath'])
        if not line_start:
            return ToolResult.invalid_params("❌ Missing required parameter: 'line_start'", missing_params=['line_start'])
        if not line_end:
            return ToolResult.invalid_params("❌ Missing required parameter: 'line_end'", missing_params=['line_end'])

        # AUTO-STAGING: If inline content is too large, auto-stage it
        if new_content:
            staged_id = auto_stage_large_content(new_content, self.working_dir)
            if staged_id:
                new_content_from_scratch = staged_id
                new_content = None

        # Get content from scratch, memory, or inline parameter
        if new_content_from_scratch:
            scratch_path = self.working_dir / ".scratch" / f"{new_content_from_scratch}.txt"
            if not scratch_path.exists():
                return ToolResult(ExecutionStatus.INVALID_PARAMS, f"❌ Scratch file '{new_content_from_scratch}' not found.")
            try:
                new_content = scratch_path.read_text(encoding='utf-8')
            except Exception as e:
                return ToolResult(ExecutionStatus.INTERNAL_ERROR, f"❌ Failed to read scratch file: {e}")
        elif new_content_from_memory:
            if not self.context_manager:
                return ToolResult(
                    ExecutionStatus.INTERNAL_ERROR,
                    "❌ Memory system not available. Cannot retrieve content from memory."
                )

            # Retrieve content from working memory
            if new_content_from_memory not in self.context_manager.working_memory:
                return ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Memory key '{new_content_from_memory}' not found. Use 'remember' tool first to store content."
                )

            new_content = self.context_manager.working_memory[new_content_from_memory]
        elif not new_content:
            return ToolResult.invalid_params(
                "❌ Must provide 'new_content', 'new_content_from_memory', or 'new_content_from_scratch' parameter",
                missing_params=['new_content', 'new_content_from_memory', 'new_content_from_scratch']
            )

        # Security validation
        if not self._is_safe_file_path(filepath):
            return ToolResult.security_blocked(f"🔒 File path blocked due to security policy: {filepath}", reason="Unsafe file path")

        full_path = self.working_dir / filepath

        try:
            # Read existing content
            lines = full_path.read_text(encoding='utf-8').splitlines()

            # Validate line range (convert to 0-based indexing)
            start_idx = line_start - 1
            end_idx = line_end  # This becomes exclusive in slicing, making line_end inclusive

            if start_idx < 0 or end_idx > len(lines) or start_idx >= end_idx:
                return ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Invalid line range: {line_start}-{line_end}. File has {len(lines)} lines."
                )

            # Get old content for diff display
            old_lines = lines[start_idx:end_idx]
            new_lines = new_content.splitlines()

            # Replace the lines
            updated_lines = lines[:start_idx] + new_lines + lines[end_idx:]
            new_content_full = "\n".join(updated_lines)

            # Preserve trailing newline if original file had one
            original_content = full_path.read_text(encoding='utf-8')
            if original_content and original_content.endswith('\n'):
                new_content_full += '\n'

            # Atomic write
            temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")
            temp_path.write_text(new_content_full, encoding='utf-8')

            with temp_path.open('r') as f:
                os.fsync(f.fileno())

            os.replace(temp_path, full_path)

            with full_path.open('r') as f:
                os.fsync(f.fileno())

            # Show rich diff
            result_message = f"✅ Replaced lines {line_start}-{line_end} in {filepath}\n"
            result_message += f"📝 Changes ({len(old_lines)} → {len(new_lines)} lines):\n"
            result_message += "─" * 50 + "\n"

            # Show removed lines
            for i, line in enumerate(old_lines):
                line_num = line_start + i
                result_message += f"-{line_num:3}│ {line}\n"

            # Show added lines
            for i, line in enumerate(new_lines):
                line_num = line_start + i
                result_message += f"+{line_num:3}│ {line}\n"

            result_message += "─" * 50

            return ToolResult.success_result(
                result_message,
                data={
                    "filepath": filepath,
                    "line_start": line_start,
                    "line_end": line_end,
                    "old_line_count": len(old_lines),
                    "new_line_count": len(new_lines),
                    "old_content": "\n".join(old_lines),
                    "new_content": new_content
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
            self.logger.error(f"File system error replacing lines in {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error replacing lines in {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")
