#!/usr/bin/env python3
"""
Execute Command Tool
====================

Pure execution logic. No UI imports.
Relies on ToolExecutor for user confirmation.
Relies on Parent Process for environment (Conda/Venv).
"""

import asyncio
import contextlib
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple, Optional

from tools.base import BaseTool, ToolResult, ToolSchema

# Default timeout for command execution (in seconds)
DEFAULT_TIMEOUT = 30
# Default timeout for long-running git operations (in seconds)
GIT_TIMEOUT = 60

class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands."""

    def __init__(
        self, working_dir: Path, preferred_env: str = None, venv_path: str = None
    ):
        super().__init__(working_dir)
        self.preferred_env = preferred_env
        self.venv_path = venv_path
        self.logger = logging.getLogger(__name__)

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
                    "description": "Optional reason for running this command",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds",
                    "default": DEFAULT_TIMEOUT,
                },
                "spawn": {
                    "type": "boolean",
                    "description": "Run in spawn mode (background, non-blocking)",
                    "default": False,
                },
            },
            required_params=["command"],
        )

    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the command with security checks asynchronously.

        Args:
            **kwargs: Arbitrary keyword arguments (command, timeout, spawn, etc).

        Returns:
            ToolResult: The result of the command execution.
        """
        command = kwargs.get("command", "").strip()
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT)
        explicit_spawn = kwargs.get("spawn", False)

        if not command:
            return ToolResult.invalid_params("Command cannot be empty")

        is_safe, safety_message = self._analyze_command_safety(command)
        if not is_safe:
            self.logger.warning("Blocked dangerous command: %s", command)
            return ToolResult.security_blocked(safety_message)

        # Spawn mode is explicit-only to avoid accidental background execution.
        spawn_mode = self._detect_spawn_mode(command, explicit_spawn)

        if spawn_mode:
            # Run in spawn mode (non-blocking, returns PID immediately)
            return await self._run_command_async(command, timeout, spawn=True)

        # Run in standard mode (await completion with streaming)
        return await self._run_command_async(command, timeout, spawn=False)

    def _detect_spawn_mode(self, command: str, explicit_spawn: bool = False) -> bool:
        """
        Detect if command should run in spawn mode.

        Spawn mode is explicit-only. We do not infer spawn from command text
        (such as '&' or 'nohup') because it can misclassify normal commands.

        Args:
            command: The command string to analyze.
            explicit_spawn: Whether explicit spawn flag was set.

        Returns:
            bool: True if spawn mode should be used.
        """
        del command  # command text intentionally ignored for spawn detection
        return bool(explicit_spawn)

    async def _run_command_async(
        self, command: str, timeout: int, spawn: bool = False
    ) -> ToolResult:
        """
        Run command asynchronously with output streaming.

        Args:
            command: The command to run.
            timeout: Maximum execution time in seconds.
            spawn: If True, returns immediately without awaiting completion.

        Returns:
            ToolResult: The result of the execution.
        """
        process = None
        stdout_task = None
        stderr_task = None

        try:
            env = os.environ.copy()
            needs_shell = self._requires_shell(command)

            if spawn:
                scratch_dir = self.working_dir / ".scratch"
                scratch_dir.mkdir(parents=True, exist_ok=True)
                log_path = scratch_dir / f"spawn_{int(time.time() * 1000)}.log"
                log_file = log_path.open("ab")
                try:
                    if needs_shell:
                        process = await asyncio.create_subprocess_shell(
                            command,
                            cwd=self.working_dir,
                            stdout=log_file,
                            stderr=log_file,
                            env=env,
                            executable=(
                                "/bin/bash" if os.path.exists("/bin/bash") else None
                            ),
                        )
                    else:
                        args = shlex.split(command)
                        process = await asyncio.create_subprocess_exec(
                            args[0],
                            *args[1:],
                            cwd=self.working_dir,
                            stdout=log_file,
                            stderr=log_file,
                            env=env,
                        )
                finally:
                    log_file.close()

                self.logger.debug(
                    "Spawned process PID %s: %s (log: %s)",
                    process.pid,
                    command,
                    log_path,
                )
                return ToolResult.success_result(
                    f"✅ Process spawned with PID {process.pid} (log: {log_path})",
                    data={
                        "pid": process.pid,
                        "command": command,
                        "log_path": str(log_path),
                    },
                )

            # Create the process with async subprocess (non-spawn)
            if needs_shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    cwd=self.working_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    executable=("/bin/bash" if os.path.exists("/bin/bash") else None),
                )
            else:
                args = shlex.split(command)
                process = await asyncio.create_subprocess_exec(
                    args[0],
                    *args[1:],
                    cwd=self.working_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

            self.logger.debug("Started process PID %s: %s", process.pid, command)

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
                await self._cleanup_process(process, stdout_task, stderr_task)
                return ToolResult.timeout(f"Command timed out after {timeout}s")

            stdout_task_result, stderr_task_result = await asyncio.gather(
                stdout_task, stderr_task
            )

            # Format result with streamed output
            return self._format_async_result(
                command, process.returncode, stdout_task_result, stderr_task_result
            )

        except asyncio.CancelledError:
            # Ensure subprocess pipes/process are cleaned up before propagating cancel.
            await self._cleanup_process(process, stdout_task, stderr_task)
            raise
        except Exception as e:  # pylint: disable=broad-exception-caught
            await self._cleanup_process(process, stdout_task, stderr_task)
            self.logger.error("Command execution error: %s", e, exc_info=True)
            return ToolResult.internal_error(f"Execution failed: {str(e)}")

    async def _cleanup_process(self, process, stdout_task, stderr_task) -> None:
        """
        Best-effort subprocess cleanup for timeout/cancellation paths.
        """
        if process is not None and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(asyncio.CancelledError, ProcessLookupError):
                await process.wait()

        for task in (stdout_task, stderr_task):
            if task is not None and not task.done():
                task.cancel()

        for task in (stdout_task, stderr_task):
            if task is None:
                continue
            with contextlib.suppress(asyncio.CancelledError):
                await task

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
                logger.debug(f"{stream_name}: {line_str}")
        except Exception as e:
            logger.error("Error streaming %s: %s", stream_name, e)

        return "\n".join(output_lines)

    def _format_async_result(
        self,
        command: str,
        return_code: int,
        stdout: str,
        stderr: str,
    ) -> ToolResult:
        """
        Format the async subprocess result into a ToolResult.

        Args:
            command: The executed command.
            return_code: The process exit code.
            stdout: The captured stdout.
            stderr: The captured stderr.

        Returns:
            ToolResult: Formatted result.
        """
        output_parts = [f"Command: {command}", f"Exit Code: {return_code}"]

        if stdout:
            output_parts.append(f"\nSTDOUT:\n{stdout}")
        if stderr:
            output_parts.append(f"\nSTDERR:\n{stderr}")

        output_str = "\n".join(output_parts)

        if return_code == 0:
            return ToolResult.success_result(output_str)

        return ToolResult.command_failed(output_str, return_code)

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

    def _requires_shell(self, command: str) -> bool:
        """
        Check if command requires shell features (pipes, redirects, etc).

        Args:
            command: The command string.

        Returns:
            bool: True if shell is required.
        """
        shell_indicators = ["|", ">", "<", ";", "$", "`", "*", "?", "&"]
        return any(indicator in command for indicator in shell_indicators)

    def _format_result(
        self, command: str, result: subprocess.CompletedProcess
    ) -> ToolResult:
        """
        Format the subprocess result into a ToolResult.
        Kept for backward compatibility but no longer used by default.

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
