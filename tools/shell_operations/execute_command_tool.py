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
import re
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any

from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus
from typing import List, Tuple, Dict, Any

from tools.base import BaseTool, ToolSchema, ToolResult


class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands."""

    def __init__(
        self, working_dir: Path, preferred_env: str = None, venv_path: str = None
    ):
        super().__init__(working_dir)
        # Environment hints are kept for logging/future use,
        # but strictly not used for injection to avoid shell compatibility issues.
        self.preferred_env = preferred_env
        self.venv_path = venv_path

    def _analyze_command_safety(self, command: str) -> Tuple[bool, str]:
        """Analyze a shell command for potential security risks."""

        # Clearly dangerous patterns that should always be blocked
        DANGEROUS_PATTERNS = [
            (r"\brm\s+-rf\s+/", "Root directory deletion"),
            (r"\brm\s+-rf\s+\.\./", "Directory traversal deletion"),
            (r"\b(format|dd)\s+[^\s]*\s*/dev/", "Disk destruction"),
            (r"\b(>\s*/dev/sda|>\s*/dev/null)", "Disk overwriting"),
            (r"\bcurl\s+.*\|\s*bash", "Remote code execution"),
            (r"\bwget\s+.*\|\s*bash", "Remote code execution"),
            (r"\bsudo\s+", "Privilege escalation"),
            (r"\b(chmod|chown)\s+777", "Overly permissive permissions"),
        ]

        # Check for dangerous patterns
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Dangerous command pattern detected: {description}"

        return True, "Command appears safe"

    def _is_safe_simple_command(self, command: str) -> bool:
        """Check if command is a simple, safe command without complex operators."""
        # Simple commands without shell operators are generally safer
        SIMPLE_COMMANDS = [
            "ls",
            "pwd",
            "echo",
            "cat",
            "grep",
            "find",
            "which",
            "git",
            "python",
            "python3",
            "pip",
            "pip3",
            "bandit",
            "radon",
            "flake8",
            "pylint",
            "mypy",
            "tokei",
            "rg",
            "fd",
        ]

        try:
            tokens = shlex.split(command)
            if tokens and tokens[0] in SIMPLE_COMMANDS:
                return True
        except ValueError:
            pass
        return False

    @property
    def schema(self) -> ToolSchema:
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
        command = kwargs.get("command", "").strip()
        timeout = kwargs.get("timeout", 30)

        if not command:
            return ToolResult.invalid_params("Command cannot be empty")

        # Security Analysis
        is_safe, safety_message = self._analyze_command_safety(command)
        if not is_safe:
            self.logger.warning(f"Blocked dangerous command: {command}")
            return ToolResult.security_blocked(safety_message)

        # Execution Logic
        try:
            # Use os.environ.copy() to inherit the current environment (Conda/Venv)
            env = os.environ.copy()

            # Force shell=True to support pipes (|), redirects (>), and chains (&&)
            # Security Note: The ToolExecutor has already obtained user confirmation for this command.
            # Additional safety analysis performed above.
            # Security Mitigation: Pre-execution analysis blocks dangerous command patterns
            # This provides defense in depth against shell injection attacks
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                executable="/bin/bash" if os.path.exists("/bin/bash") else None,
            )

            # Result Formatting
            output_str = f"Command: {command}\nExit Code: {result.returncode}\n"
            if result.stdout:
                output_str += f"\nSTDOUT:\n{result.stdout}"
            if result.stderr:
                output_str += f"\nSTDERR:\n{result.stderr}"

            if result.returncode == 0:
                return ToolResult.success_result(output_str)
            else:
                return ToolResult.command_failed(output_str, result.returncode)

        except subprocess.TimeoutExpired:
            return ToolResult.command_failed(f"Command timed out after {timeout}s", -1)
        except subprocess.CalledProcessError as e:
            return ToolResult.command_failed(f"Command failed: {e}", e.returncode)
        except PermissionError as e:
            return ToolResult(
                ExecutionStatus.EXTERNAL_ERROR,
                f"Permission denied: {str(e)}",
                {
                    "error_type": "PermissionError",
                    "command": command,
                    "details": str(e),
                },
            )
        except FileNotFoundError as e:
            return ToolResult(
                ExecutionStatus.EXTERNAL_ERROR,
                f"Command not found: {str(e)}",
                {
                    "error_type": "FileNotFoundError",
                    "command": command,
                    "details": str(e),
                },
            )
        except Exception as e:
            self.logger.error(f"Command execution error: {e}", exc_info=True)
            return ToolResult.internal_error(f"Execution failed: {str(e)}")
