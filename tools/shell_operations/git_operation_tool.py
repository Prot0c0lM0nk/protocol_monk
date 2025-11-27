#!/usr/bin/env python3
"""
Git Operations Tool - Handle git commands for MonkCode Agent
Adapted from the original CodeAssistant class functionality.
"""

import subprocess
import logging
from typing import Dict, Any
from pathlib import Path

from tools.base import BaseTool, ToolSchema, ToolResult, ExecutionStatus

# Default timeout for git operations (in seconds)
DEFAULT_GIT_TIMEOUT = 60


class GitOperationTool(BaseTool):
    """Tool for executing git operations with confirmation."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)
        # Map of supported git operations to their command lists (for shell=False)
        self._git_commands = {
            'status': ['git', 'status'],
            'add': ['git', 'add', '.'],
            'commit': ['git', 'commit', '-m', 'AI assistant changes'],
            'push': ['git', 'push'],
            'pull': ['git', 'pull'],
            'log': ['git', 'log', '--oneline', '-10']
        }

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="git_operation",
            description="Execute git operations (status, add, commit, push, pull, log)",
            parameters={
                "operation": {
                    "type": "string",
                    "description": "Git operation to perform",
                    "enum": ["status", "add", "commit", "push", "pull", "log"]
                },
                "commit_message": {
                    "type": "string",
                    "description": "Custom commit message (only used with 'commit' operation)",
                    "default": "AI assistant changes"
                }
            },
            required_params=["operation"]
        )

    def execute(self, **kwargs) -> ToolResult:
        """Execute a git operation with confirmation."""
        operation = kwargs.get("operation")
        commit_message = kwargs.get("commit_message", "AI assistant changes")

        # Validate required parameters
        if not operation:
            return ToolResult.invalid_params("❌ Missing required parameter: 'operation'", missing_params=['operation'])

        # Validate operation
        if operation not in self._git_commands:
            available_ops = ", ".join(self._git_commands.keys())
            return ToolResult.invalid_params(
                f"❌ Unknown git operation: {operation}. Available: {available_ops}",
                missing_params=['operation']
            )

        # Get the git command list (copy to avoid mutating the original)
        command = self._git_commands[operation].copy()

        # Handle custom commit message (safely via list form)
        if operation == "commit" and commit_message != "AI assistant changes":
            command = ['git', 'commit', '-m', commit_message]

        # Set timeout
        timeout = DEFAULT_GIT_TIMEOUT

        try:
            result = subprocess.run(
                command,
                shell=False,  # SECURITY: Prevent shell injection
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"
            output += f"Exit code: {result.returncode}"

            status_icon = "✅" if result.returncode == 0 else "❌"

            # Provide helpful hint for credential errors
            if result.returncode == 128 and operation in ['push', 'pull']:
                output += "\n💡 Hint: Exit code 128 often means authentication failed. "
                output += "Consider configuring a credential helper or using SSH keys."

            # Add operation-specific success messages
            if result.returncode == 0:
                operation_messages = {
                    'status': "📊 Repository status retrieved",
                    'add': "➕ Files staged for commit",
                    'commit': "💾 Changes committed to repository",
                    'push': "🚀 Changes pushed to remote repository",
                    'pull': "⬇️ Changes pulled from remote repository",
                    'log': "📜 Recent commit history retrieved"
                }
                success_msg = operation_messages.get(operation, f"Git {operation} completed")
                formatted_output = f"{status_icon} {success_msg}\n{output}"

                return ToolResult.success_result(
                    formatted_output,
                    data={
                        "operation": operation,
                        "command": ' '.join(command),  # Convert list to string for display
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }
                )
            else:
                formatted_output = f"{status_icon} Git {operation} failed\n{output}"

                return ToolResult.command_failed(
                    formatted_output,
                    exit_code=result.returncode,
                    data={
                        "operation": operation,
                        "command": ' '.join(command),
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }
                )

        except subprocess.TimeoutExpired:
            return ToolResult.timeout(f"⏰ Git {operation} timed out after {timeout} seconds")
        except FileNotFoundError:
            # This occurs if 'git' is not installed or not in PATH
            return ToolResult.command_failed("❌ 'git' command not found. Is Git installed and in your PATH?", exit_code=127)
        except Exception as e:
            self.logger.error(f"Unexpected error executing git {operation}: {e}", exc_info=True)
            return ToolResult.internal_error(f"❌ Unexpected error executing git {operation}: {e}")

    def get_supported_operations(self) -> list:
        """Return list of supported git operations."""
        return list(self._git_commands.keys())
