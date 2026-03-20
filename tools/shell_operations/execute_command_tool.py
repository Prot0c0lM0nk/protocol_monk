import subprocess
from typing import Dict, Any, Tuple

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.config.settings import Settings
from protocol_monk.tools.output_contract import build_process_output
from protocol_monk.tools.shell_operations.process_runner import run_shell_command


class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        # Use workspace root from settings
        self.working_dir = settings.workspace_root

    @property
    def name(self) -> str:
        return "execute_command"

    @property
    def description(self) -> str:
        return "Execute a shell command in the workspace."

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "description": {
                    "type": "string",
                    "description": "Reason for running this command",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30,
                },
            },
            "required": ["command", "description"],
        }

    @property
    def requires_confirmation(self) -> bool:
        return True  # Shell commands are dangerous!

    async def run(self, **kwargs) -> Any:
        command = kwargs.get("command", "").strip()
        description = kwargs.get("description", "").strip()
        timeout = kwargs.get("timeout", 30)

        if not command:
            raise ToolError(
                "Command cannot be empty",
                user_hint="Please provide a shell command to execute.",
            )

        # Security Check
        is_safe, safety_message = self._analyze_command_safety(command)
        if not is_safe:
            raise ToolError(
                f"Security Blocked: {safety_message}",
                user_hint=f"Blocked unsafe command pattern: {safety_message}.",
                details={"command": command, "reason": safety_message},
            )

        try:
            result = await run_shell_command(
                command,
                cwd=self.working_dir,
                timeout_seconds=timeout,
            )

            if result.returncode != 0:
                raise ToolError(
                    f"Command failed with exit code {result.returncode}",
                    user_hint=f"Command failed (exit {result.returncode}).",
                    details={
                        "command": command,
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                )

            return build_process_output(
                result_type="command_execution",
                summary=self._build_summary(result.stdout, result.stderr, result.returncode),
                command=command,
                cwd=str(self.working_dir),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                extra_data={
                    "description": description,
                    "timeout_seconds": timeout,
                    "shell": True,
                },
                parse_json_streams=True,
            )

        except subprocess.TimeoutExpired:
            raise ToolError(
                f"Command timed out after {timeout}s",
                user_hint=f"Command timed out after {timeout}s.",
                details={"command": command, "timeout": timeout},
            )
        except TimeoutError:
            raise ToolError(
                f"Command timed out after {timeout}s",
                user_hint=f"Command timed out after {timeout}s.",
                details={"command": command, "timeout": timeout},
            )
        except Exception as e:
            if isinstance(e, ToolError):
                raise
            raise ToolError(
                f"Command execution error: {str(e)}",
                user_hint="Shell command failed unexpectedly.",
                details={"command": command, "error": str(e)},
            )

    def _analyze_command_safety(self, command: str) -> Tuple[bool, str]:
        import re

        dangerous_patterns = [
            (r"\brm\s+-rf\s+/", "Root directory deletion"),
            (r"\brm\s+-rf\s+\.\./", "Directory traversal deletion"),
            (r"\bsudo\s+", "Privilege escalation"),
        ]
        for pattern, desc in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, desc
        return True, "Safe"

    def _build_summary(self, stdout: str, stderr: str, exit_code: int) -> str:
        stripped_stdout = str(stdout or "").strip()
        stripped_stderr = str(stderr or "").strip()

        import json

        for text in (stripped_stdout, stripped_stderr):
            if not text:
                continue
            try:
                json.loads(text)
                return "Executed shell command successfully with JSON output."
            except json.JSONDecodeError:
                continue

        return f"Executed shell command successfully with exit code {exit_code}."
