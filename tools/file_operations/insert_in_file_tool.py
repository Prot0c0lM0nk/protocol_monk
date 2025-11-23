#!/usr/bin/env python3
"""
Insert In File Tool - Insert content after a specific line in a file.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from agent import exceptions
from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
from tools.file_operations.auto_stage_large_content import auto_stage_large_content


class InsertInFileTool(BaseTool):
    """Tool for inserting content after a specific line in a file."""

    def __init__(self, working_dir: Path, context_manager=None):
        super().__init__(working_dir)
        self.context_manager = context_manager
        self.logger = logging.getLogger(__name__)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="insert_in_file",
            description="[USE THIS FOR INSERTING IN MIDDLE] Insert content after a specific line. Perfect for adding imports, class methods, or code between existing lines. For large content, use 'remember' tool first.",
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file (relative to working directory)"
                },
                "after_line": {
                    "type": "string",
                    "description": "Exact line content to insert after (must match exactly including whitespace)"
                },
                "content": {
                    "type": "string",
                    "description": "Content to insert after the specified line (for small content). For large content, use content_from_memory instead."
                },
                "content_from_memory": {
                    "type": "string",
                    "description": "Memory key containing the content to insert (use 'remember' tool first to store large content)"
                },
                "content_from_scratch": {
                    "type": "string",
                    "description": "Scratch ID for staged code block (system auto-stages code blocks from conversational output)"
                }
            },
            required_params=["filepath", "after_line"]
        )

    
    def execute(self, **kwargs) -> ToolResult:
        """Insert content after a specific line in a file."""
        filepath = kwargs.get("filepath")
        after_line = kwargs.get("after_line")
        content = kwargs.get("content")
        content_from_memory = kwargs.get("content_from_memory")
        content_from_scratch = kwargs.get("content_from_scratch")

        # Validate required parameters
        if not filepath:
            return ToolResult.invalid_params("❌ Missing required parameter: 'filepath'", missing_params=['filepath'])
        if not after_line:
            return ToolResult.invalid_params("❌ Missing required parameter: 'after_line'", missing_params=['after_line'])

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
                return ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Scratch file '{content_from_scratch}' not found."
                )
            try:
                content = scratch_path.read_text(encoding='utf-8')
            except Exception as e:
                return ToolResult(ExecutionStatus.INTERNAL_ERROR, f"❌ Failed to read scratch file: {e}")
        elif content_from_memory:
            if not self.context_manager:
                return ToolResult(
                    ExecutionStatus.INTERNAL_ERROR,
                    "❌ Memory system not available. Cannot retrieve content from memory."
                )

            # Retrieve content from working memory
            if content_from_memory not in self.context_manager.working_memory:
                return ToolResult(
                    ExecutionStatus.INVALID_PARAMS,
                    f"❌ Memory key '{content_from_memory}' not found. Use 'remember' tool first to store content."
                )

            content = self.context_manager.working_memory[content_from_memory]
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
            lines = full_path.read_text(encoding='utf-8').splitlines()

            # Find the insertion point
            insert_index = -1
            for i, line in enumerate(lines):
                if line == after_line:
                    insert_index = i + 1  # Insert AFTER this line
                    break

            if insert_index == -1:
                return ToolResult(
                    ExecutionStatus.COMMAND_FAILED,
                    f"❌ Line not found: '{after_line}'"
                )

            # Split the content to insert
            content_lines = content.splitlines()

            # Create new content with insertion
            new_lines = lines[:insert_index] + content_lines + lines[insert_index:]
            new_content = "\n".join(new_lines)

            # Atomic write
            temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")

            with temp_path.open('w', encoding='utf-8') as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())

            os.replace(temp_path, full_path)

            # Show insertion context
            context_before = 2
            context_after = 2
            start_show = max(0, insert_index - context_before)
            end_show = min(len(new_lines), insert_index + len(content_lines) + context_after)

            result_message = f"✅ Inserted {len(content_lines)} line(s) after line {insert_index} in {filepath}\n"
            result_message += f"📝 Insertion context:\n{'-' * 50}\n"

            for i in range(start_show, end_show):
                line_num = i + 1
                line_content = new_lines[i]

                if insert_index <= i < insert_index + len(content_lines):
                    # Inserted lines - highlight
                    result_message += f"+{line_num:3}│ {line_content}\n"
                else:
                    # Context lines
                    result_message += f" {line_num:3}│ {line_content}\n"

            result_message += f"{'-' * 50}"

            return ToolResult.success_result(
                result_message,
                data={
                    "filepath": filepath,
                    "insert_after_line": insert_index,
                    "lines_inserted": len(content_lines),
                    "inserted_content": content
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
            self.logger.error(f"File system error inserting into {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ File system error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error inserting into {filepath}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error: {e}")
