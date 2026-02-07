#!/usr/bin/env python3
"""
Git Operations Tool - Handle git commands for MonkCode Agent.
Adapted from the original CodeAssistant class functionality.
"""

import asyncio
import contextlib
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from tools.base import BaseTool, ToolResult, ToolSchema

# Default timeout for git operations (in seconds)
DEFAULT_GIT_TIMEOUT = 60


class GitOperationTool(BaseTool):
    """Tool for executing git operations with confirmation."""

    def __init__(self, working_dir: Path):
        super().__init__(working_dir)
        self.logger = logging.getLogger(__name__)
        # Map of supported git operations to their command lists
        self._git_commands = {
            "status": ["git", "status"],
            "add": ["git", "add", "."],
            "commit": ["git", "commit", "-m", "AI assistant changes"],
            "push": ["git", "push"],
            "pull": ["git", "pull"],
            "log": ["git", "log", "--oneline", "-10"],
        }

    @property
    def schema(self) -> ToolSchema:
        """
        Return the tool schema.

        Returns:
            ToolSchema: The definition of the tool's interface.
        """
        return ToolSchema(
            name="git_operation",
            description=(
                "Execute git operations (status, add, commit, push, pull, log)"
            ),
            parameters={
                "operation": {
                    "type": "string",
                    "description": "Git operation to perform",
                    "enum": ["status", "add", "commit", "push", "pull", "log"],
                },
                "commit_message": {
                    "type": "string",
                    "description": ("Custom commit message (only used with 'commit')"),
                    "default": "AI assistant changes",
                },
            },
            required_params=["operation"],
        )

    async def execute(self, **kwargs) -> ToolResult:
        """
        Orchestrate the git operation asynchronously.

        Args:
            **kwargs: Arbitrary keyword arguments (operation, etc).

        Returns:
            ToolResult: The result of the git operation.
        """
        # 1. Validate Operation
        operation, error = self._validate_operation(kwargs.get("operation"))
        if error:
            return error

        # 2. Build Command
        # pylint: disable=unpacking-non-sequence
        command = self._build_command(
            operation, kwargs.get("commit_message", "AI assistant changes")
        )

        # 3. Execute
        return await self._execute_git_command_async(operation, command)

    def _validate_operation(
        self, operation: Optional[str]
    ) -> Tuple[Optional[str], Optional[ToolResult]]:
        """
        Check if operation is valid and supported.

        Args:
            operation: The name of the git operation.

        Returns:
            Tuple[Optional[str], Optional[ToolResult]]: Validated operation
            name or None, and an error result if invalid.
        """
        if not operation:
            return None, ToolResult.invalid_params(
                "❌ Missing required parameter: 'operation'",
                missing_params=["operation"],
            )

        if operation not in self._git_commands:
            available_ops = ", ".join(self._git_commands.keys())
            return None, ToolResult.invalid_params(
                f"❌ Unknown git operation: {operation}. "
                f"Available: {available_ops}",
                missing_params=["operation"],
            )

        return operation, None

    def _build_command(self, operation: str, commit_message: str) -> List[str]:
        """
        Construct the git command list.

        Args:
            operation: The validated git operation.
            commit_message: Optional message for commits.

        Returns:
            List[str]: The command list for subprocess.
        """
        command = self._git_commands[operation].copy()

        if operation == "commit" and commit_message != "AI assistant changes":
            return ["git", "commit", "-m", commit_message]

        return command

    async def _execute_git_command_async(
        self, operation: str, command: List[str], timeout: int = DEFAULT_GIT_TIMEOUT
    ) -> ToolResult:
        """
        Run the git subprocess asynchronously with output streaming.

        Args:
            operation: The name of the operation (for logging).
            command: The actual command list to execute.
            timeout: Maximum execution time in seconds.

        Returns:
            ToolResult: The execution result.
        """
        try:
            self.logger.debug("Starting git %s: %s", operation, " ".join(command))

            # Create async subprocess
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self.logger.debug("Git process PID %s started: %s", process.pid, command)

            # Always stream output to prevent buffer overflow deadlocks
            stdout_task = asyncio.create_task(
                self._stream_output(process.stdout, "STDOUT", self.logger)
            )
            stderr_task = asyncio.create_task(
                self._stream_output(process.stderr, "STDERR", self.logger)
            )

            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                stdout_task.cancel()
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stdout_task
                    await stderr_task
                return ToolResult.timeout(
                    f"⏰ Git {operation} timed out after {timeout} seconds"
                )

            stdout_result, stderr_result = await asyncio.gather(
                stdout_task, stderr_task
            )

            return self._format_result(
                operation, command, process.returncode, stdout_result, stderr_result
            )

        except FileNotFoundError:
            return ToolResult.command_failed(
                "❌ 'git' command not found. Is Git installed?", exit_code=127
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Git execution error: %s", e, exc_info=True)
            return ToolResult.internal_error(f"❌ Error executing git {operation}: {e}")

    async def _stream_output(
        self, stream, stream_name: str, logger
    ) -> str:
        """
        Stream output from a subprocess pipe incrementally.

        Args:
            stream: The asyncio stream to read from.
            stream_name: Name for logging (STDOUT/STDERR).
            logger: Logger instance.

        Returns:
            str: All output collected from the stream.
        """
        output_lines = []
        try:
            async for line in stream:
                line_str = line.decode("utf-8", errors="replace").rstrip()
                output_lines.append(line_str)
                logger.debug(f"Git {stream_name}: {line_str}")
        except Exception as e:
            logger.error("Error streaming %s: %s", stream_name, e)

        return "\n".join(output_lines)

    def _format_result(
        self, operation: str, command: List[str], return_code: int, stdout: str, stderr: str
    ) -> ToolResult:
        """
        Format success or failure output.

        Args:
            operation: The operation name.
            command: The executed command list.
            return_code: The process exit code.
            stdout: Captured stdout output.
            stderr: Captured stderr output.

        Returns:
            ToolResult: The formatted result.
        """
        output = self._build_output_string(return_code, stdout, stderr, operation)
        status_icon = "✅" if return_code == 0 else "❌"

        if return_code == 0:
            data = {
                "operation": operation,
                "command": " ".join(command),
                "exit_code": return_code,
                "stdout": stdout,
                "stderr": stderr,
            }
            return ToolResult.success_result(f"{status_icon} {output}", data=data)

        return ToolResult.command_failed(
            f"{status_icon} {output}", exit_code=return_code
        )

    def _build_output_string(
        self, return_code: int, stdout: str, stderr: str, operation: str
    ) -> str:
        """
        Helper to build the descriptive output string.

        Args:
            return_code: The process exit code.
            stdout: Captured stdout output.
            stderr: Captured stderr output.
            operation: The operation name.

        Returns:
            str: The formatted output string.
        """
        parts = []

        # Operation-specific headers
        headers = {
            "status": "📊 Repository status retrieved",
            "add": "➕ Files staged for commit",
            "commit": "💾 Changes committed",
            "push": "🚀 Changes pushed",
            "pull": "⬇️ Changes pulled",
            "log": "📜 Commit history",
        }

        if return_code == 0:
            parts.append(headers.get(operation, f"Git {operation} completed"))
        else:
            parts.append(f"Git {operation} failed")

        # Standard output
        if stdout:
            parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            parts.append(f"STDERR:\n{stderr}")

        # Hints
        if return_code == 128 and operation in ["push", "pull"]:
            parts.append("💡 Hint: Exit code 128 often means authentication failed.")

        return "\n".join(parts)

    def get_supported_operations(self) -> list:
        """
        Return list of supported git operations.

        Returns:
            list: List of operation names.
        """
        return list(self._git_commands.keys())
