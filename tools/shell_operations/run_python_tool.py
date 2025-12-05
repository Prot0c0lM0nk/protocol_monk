#!/usr/bin/env python3
"""
Run Python Tool - Execute Python code by leveraging the ExecuteCommandTool.
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Tuple

from tools.base import BaseTool, ToolResult, ToolSchema
from tools.shell_operations.execute_command_tool import ExecuteCommandTool


class RunPythonTool(BaseTool):
    """Tool for running Python code by writing it to a temp script."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)
        self.command_executor = ExecuteCommandTool(working_dir)

    @property
    def schema(self) -> ToolSchema:
        """
        Return the tool schema.

        Returns:
            ToolSchema: The definition of the tool's interface.
        """
        return ToolSchema(
            name="run_python",
            description="Execute Python code in a temporary script.",
            parameters={
                "script_content": {
                    "type": "string",
                    "description": "The Python code to execute.",
                },
                "script_name": {
                    "type": "string",
                    "description": "Optional name for the temp script file.",
                    "default": "temp_python_script.py",
                },
            },
            required_params=["script_content"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """
        Orchestrate the python execution.

        Args:
            **kwargs: Arbitrary keyword arguments (script_content, etc).

        Returns:
            ToolResult: The result of the execution.
        """
        content = kwargs.get("script_content")
        name = kwargs.get("script_name", "temp_python_script.py")

        if not content:
            return ToolResult.invalid_params(
                "❌ Missing parameter: 'script_content'",
                missing_params=["script_content"],
            )

        # 1. Write Script
        file_path, error = self._write_temp_script(name, content)
        if error:
            return error

        # 2. Execute Script
        try:
            # pylint: disable=unpacking-non-sequence
            return self._run_script_execution(file_path, content)
        finally:
            self._cleanup(file_path)

    def _write_temp_script(
        self, name: str, content: str
    ) -> Tuple[Optional[Path], Optional[ToolResult]]:
        """
        Safely write the content to a temporary file.

        Args:
            name: The name of the file.
            content: The python code content.

        Returns:
            Tuple[Optional[Path], Optional[ToolResult]]: The file path and
            optional error result.
        """
        temp_path = self.working_dir / name
        rel_path = str(temp_path.relative_to(self.working_dir))

        if not self._is_safe_file_path(rel_path):
            return None, ToolResult.security_blocked(
                f"File path is outside the working directory: {name}"
            )

        try:
            temp_path.write_text(content, encoding="utf-8")
            self.logger.info("Created temporary Python script: %s", temp_path)
            return temp_path, None
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Failed to write temp script: %s", e)
            return None, ToolResult.internal_error(
                f"❌ Failed to write script: {e}"
            )

    def _run_script_execution(
        self, file_path: Path, original_content: str
    ) -> ToolResult:
        """
        Delegate execution to ExecuteCommandTool.

        Args:
            file_path: Path to the script file.
            original_content: The original source code for context.

        Returns:
            ToolResult: The execution result.
        """
        command = f"{sys.executable} {file_path.name}"

        result = self.command_executor.execute(
            command=command, description="Executing temporary Python script."
        )

        # Inject context
        if hasattr(result, "data") and isinstance(result.data, dict):
            result.data["script_content"] = original_content

        return result

    def _cleanup(self, file_path: Path):
        """
        Remove the temporary file.

        Args:
            file_path: The path to remove.
        """
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                self.logger.info("Cleaned up temporary script: %s", file_path)
            except OSError as e:
                self.logger.warning(
                    "Failed to clean up script %s: %s", file_path, e
                )