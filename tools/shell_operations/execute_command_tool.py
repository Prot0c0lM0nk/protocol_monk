import subprocess
from typing import Dict, Any, Tuple

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.config.settings import Settings


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
        # Note: In a real async system, we should use asyncio.create_subprocess_shell
        # But to keep logic consistent with your existing code, we wrap the sync call.
        return self._execute_sync(**kwargs)

    def _execute_sync(self, **kwargs) -> str:
        command = kwargs.get("command", "").strip()
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
            # We enforce CWD to be the workspace
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
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

            output = f"Exit Code: {result.returncode}\n"
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"

            return output

        except subprocess.TimeoutExpired:
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
