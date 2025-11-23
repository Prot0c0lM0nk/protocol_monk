#!/usr/bin/env python3
"""
Execute Command Tool
====================

Pure execution logic. No UI imports.
Relies on ToolExecutor for user confirmation.
Relies on Parent Process for environment (Conda/Venv).
"""

import subprocess
import os
import shlex
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any

from tools.base import BaseTool, ToolSchema, ToolResult

class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands."""

    def __init__(self, working_dir: Path, preferred_env: str = None, venv_path: str = None):
        super().__init__(working_dir)
        # Environment hints are kept for logging/future use, 
        # but strictly not used for injection to avoid shell compatibility issues.
        self.preferred_env = preferred_env
        self.venv_path = venv_path

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="execute_command",
            description="Execute a shell command in the working directory.",
            parameters={
                "command": {"type": "string", "description": "The shell command to execute"},
                "description": {"type": "string", "description": "Reason for running this command"},
                "timeout": {"type": "number", "description": "Timeout in seconds", "default": 30}
            },
            required_params=["command", "description"]
        )

    def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command", "").strip()
        timeout = kwargs.get("timeout", 30)
        
        if not command:
            return ToolResult.invalid_params("Command cannot be empty")

        # Execution Logic
        try:
            # Use os.environ.copy() to inherit the current environment (Conda/Venv)
            env = os.environ.copy()
            
            # Force shell=True to support pipes (|), redirects (>), and chains (&&)
            # Security Note: The ToolExecutor has already obtained user confirmation for this command.
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                executable="/bin/bash" if os.path.exists("/bin/bash") else None
            )

            # Result Formatting
            output_str = f"Command: {command}\nExit Code: {result.returncode}\n"
            if result.stdout: output_str += f"\nSTDOUT:\n{result.stdout}"
            if result.stderr: output_str += f"\nSTDERR:\n{result.stderr}"

            if result.returncode == 0:
                return ToolResult.success_result(output_str)
            else:
                return ToolResult.command_failed(output_str, result.returncode)

        except subprocess.TimeoutExpired:
            return ToolResult.command_failed(f"Command timed out after {timeout}s", -1)
        except Exception as e:
            self.logger.error(f"Command execution error: {e}", exc_info=True)
            return ToolResult.internal_error(f"Execution failed: {str(e)}")