#!/usr/bin/env python3
"""
Execute Command Tool
====================

Pure execution logic. No UI imports.
Relies on ToolExecutor for user confirmation.
Relies on Parent Process for environment (Conda/Venv).
"""

import shlex
import os
import re
import subprocess
from pathlib import Path
from typing import Tuple

from tools.base import BaseTool, ToolResult, ToolSchema


class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands."""

    def __init__(
        self, working_dir: Path, preferred_env: str = None, venv_path: str = None
    ):
        super().__init__(working_dir)
        self.preferred_env = preferred_env
        self.venv_path = venv_path

    @property
    def schema(self) -> ToolSchema:
        """
        Return the tool schema.

        Returns:
            ToolSchema: The definition of the tool's interface.
        """
        return ToolSchema(
            name="execute_command",
            description="Execute a shell command in the working directory.",
            parameters={
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "description": {
                    "type": "string",
                    "description": "Reason for running this command",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds",
                    "default": 30,
                },
            },
            required_params=["command", "description"],
        )

    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the command with security checks.

        Args:
            **kwargs: Arbitrary keyword arguments (command, timeout, etc).

        Returns:
            ToolResult: The result of the command execution.
        """
        command = kwargs.get("command", "").strip()
        timeout = kwargs.get("timeout", 30)

        if not command:
            return ToolResult.invalid_params("Command cannot be empty")

        is_safe, safety_message = self._analyze_command_safety(command)
        if not is_safe:
            self.logger.warning("Blocked dangerous command: %s", command)
            return ToolResult.security_blocked(safety_message)

        return self._run_command(command, timeout)

    def _analyze_command_safety(self, command: str) -> Tuple[bool, str]:
        """
        Analyze a shell command for potential security risks.

        Args:
            command: The command string to analyze.

        Returns:
            Tuple[bool, str]: (Is safe, Reason/Message).
        """
        dangerous_patterns = [
            (r"\brm\s+-rf\s+/", "Root directory deletion"),
            (r"\brm\s+-rf\s+\.\./", "Directory traversal deletion"),
            (r"\b(format|dd)\s+[^\s]*\s*/dev/", "Disk destruction"),
            (r"\b(>\s*/dev/sda|>\s*/dev/null)", "Disk overwriting"),
            (r"\bcurl\s+.*\|\s*bash", "Remote code execution"),
            (r"\bwget\s+.*\|\s*bash", "Remote code execution"),
            (r"\bsudo\s+", "Privilege escalation"),
            (r"\b(chmod|chown)\s+777", "Overly permissive permissions"),
        ]

        for pattern, description in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                msg = f"Dangerous command pattern detected: {description}"
                return False, msg

        return True, "Command appears safe"

    def _run_command(self, command: str, timeout: int) -> ToolResult:
        """
        Determine execution mode and run subprocess.

        Args:
            command: The command to run.
            timeout: Maximum execution time in seconds.

        Returns:
            ToolResult: The result of the execution.
        """
        try:
            env = os.environ.copy()
            needs_shell = self._requires_shell(command)

            # Hybrid Execution Strategy:
            # 1. Simple commands use shell=False (Secure)
            # 2. Complex commands (pipes/redirects) use shell=True (Risky)
            if needs_shell:
                # nosec B602: Validated by _analyze_command_safety & approval
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    check=False,
                    executable=("/bin/bash" if os.path.exists("/bin/bash") else None),
                )
            else:
                args = shlex.split(command)
                result = subprocess.run(
                    args,
                    shell=False,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    check=False,
                )

            return self._format_result(command, result)

        except subprocess.TimeoutExpired:
            return ToolResult.command_failed(f"Command timed out after {timeout}s", -1)
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Command execution error: %s", e, exc_info=True)
            return ToolResult.internal_error(f"Execution failed: {str(e)}")

    def _requires_shell(self, command: str) -> bool:
        """
        Check if command requires shell features (pipes, redirects, etc).

        Args:
            command: The command string.

        Returns:
            bool: True if shell is required.
        """
        shell_indicators = ["|", ">", "<", "&", ";", "$", "`", "*", "?"]
        return any(indicator in command for indicator in shell_indicators)

    def _format_result(
        self, command: str, result: subprocess.CompletedProcess
    ) -> ToolResult:
        """
        Format the subprocess result into a ToolResult.

        Args:
            command: The executed command.
            result: The subprocess result object.

        Returns:
            ToolResult: Formatted result.
        """
        output_parts = [f"Command: {command}", f"Exit Code: {result.returncode}"]

        if result.stdout:
            output_parts.append(f"\nSTDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"\nSTDERR:\n{result.stderr}")

        output_str = "\n".join(output_parts)

        if result.returncode == 0:
            return ToolResult.success_result(output_str)

        return ToolResult.command_failed(output_str, result.returncode)
