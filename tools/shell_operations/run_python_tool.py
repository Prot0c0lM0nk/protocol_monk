#!/usr/bin/env python3
"""
Run Python Tool - Execute Python code by leveraging the ExecuteCommandTool.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any

from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
from tools.shell_operations.execute_command_tool import ExecuteCommandTool


class RunPythonTool(BaseTool):
    """Tool for running Python code by writing it to a temporary script and executing it."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)
        self.command_executor = ExecuteCommandTool(working_dir)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="run_python",
            description="Execute Python code in a temporary script. The code should be self-contained.",
            parameters={
                "script_content": {
                    "type": "string",
                    "description": "The Python code to execute.",
                },
                "script_name": {
                    "type": "string",
                    "description": "Optional name for the temporary script file.",
                    "default": "temp_python_script.py",
                },
            },
            required_params=["script_content"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """
        Writes Python code to a temporary file and uses ExecuteCommandTool to run it.
        """
        script_content = kwargs.get("script_content")
        script_name = kwargs.get("script_name", "temp_python_script.py")

        if not script_content:
            return ToolResult.invalid_params(
                "❌ Missing required parameter: 'script_content'",
                missing_params=["script_content"],
            )

        temp_file_path = self.working_dir / script_name

        # Ensure the file path is safe (within working directory)
        if not self._is_safe_file_path(
            str(temp_file_path.relative_to(self.working_dir))
        ):
            return ToolResult.security_blocked(
                f"File path is outside the working directory: {script_name}"
            )

        try:
            # Write the Python code to the temporary file
            temp_file_path.write_text(script_content, encoding="utf-8")
            self.logger.info(f"Created temporary Python script: {temp_file_path}")

            # Construct the command to execute the script
            command = f"{sys.executable} {temp_file_path.name}"
            description = "Executing temporary Python script."

            # Delegate execution to the ExecuteCommandTool
            self.logger.info(f"Executing command: {command}")
            result = self.command_executor.execute(
                command=command, description=description
            )

            # Augment the result with Python-specific context
            if hasattr(result, "data") and isinstance(result.data, dict):
                result.data["script_content"] = script_content
            return result

        except SyntaxError as e:
            self.logger.error(f"Python syntax error: {e}", exc_info=True)
            return ToolResult(
                ExecutionStatus.EXTERNAL_ERROR,
                f"Python syntax error: {str(e)}",
                {
                    "error_type": "SyntaxError",
                    "script_name": script_name,
                    "details": str(e),
                },
            )
        except ImportError as e:
            self.logger.error(f"Python import error: {e}", exc_info=True)
            return ToolResult(
                ExecutionStatus.EXTERNAL_ERROR,
                f"Python import error: {str(e)}",
                {
                    "error_type": "ImportError",
                    "script_name": script_name,
                    "details": str(e),
                },
            )
        except PermissionError as e:
            self.logger.error(f"Permission denied: {e}", exc_info=True)
            return ToolResult(
                ExecutionStatus.EXTERNAL_ERROR,
                f"Permission denied: {str(e)}",
                {
                    "error_type": "PermissionError",
                    "script_name": script_name,
                    "details": str(e),
                },
            )
        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e}", exc_info=True)
            return ToolResult(
                ExecutionStatus.EXTERNAL_ERROR,
                f"File not found: {str(e)}",
                {
                    "error_type": "FileNotFoundError",
                    "script_name": script_name,
                    "details": str(e),
                },
            )
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred in RunPythonTool: {e}", exc_info=True
            )
            return ToolResult.internal_error(
                f"❌ An unexpected error occurred while trying to run the Python script: {e}"
            )
        finally:
            # Ensure the temporary file is cleaned up
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                    self.logger.info(f"Cleaned up temporary script: {temp_file_path}")
                except Exception as e:
                    self.logger.warning(
                        f"Failed to clean up temporary script {temp_file_path}: {e}",
                        exc_info=True,
                    )
