import subprocess
from typing import Dict, Any, List

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.config.settings import Settings


class GitOperationTool(BaseTool):
    """Tool for executing specific git operations."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.working_dir = settings.workspace_root
        self._git_commands = {
            "status": ["git", "status"],
            "add": ["git", "add", "."],
            "commit": ["git", "commit", "-m", "AI assistant changes"],
            "push": ["git", "push"],
            "pull": ["git", "pull"],
            "log": ["git", "log", "--oneline", "-10"],
        }

    @property
    def name(self) -> str:
        return "git_operation"

    @property
    def description(self) -> str:
        return "Execute git operations (status, add, commit, push, pull, log)"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": list(self._git_commands.keys()),
                    "description": "Git operation to perform",
                },
                "commit_message": {
                    "type": "string",
                    "description": "Message for commit operation",
                    "default": "AI assistant changes",
                },
            },
            "required": ["operation"],
        }

    async def run(self, **kwargs) -> Any:
        operation = kwargs.get("operation")
        commit_msg = kwargs.get("commit_message")

        if operation not in self._git_commands:
            raise ToolError(
                f"Unknown operation '{operation}'",
                user_hint=f"Unknown git operation '{operation}'.",
                details={"operation": operation},
            )

        command = self._git_commands[operation].copy()
        if operation == "commit" and commit_msg:
            # Replace default message
            command[-1] = commit_msg

        try:
            result = subprocess.run(
                command,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            if result.returncode != 0:
                raise ToolError(
                    f"Git command failed with exit code {result.returncode}",
                    user_hint=f"Git {operation} failed (exit {result.returncode}).",
                    details={
                        "operation": operation,
                        "command": command,
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                )

            output = f"Exit Code: {result.returncode}\n"
            if result.stdout:
                output += f"{result.stdout}\n"
            if result.stderr:
                output += f"{result.stderr}\n"
            return output

        except Exception as e:
            if isinstance(e, ToolError):
                raise
            raise ToolError(
                f"Git Error: {str(e)}",
                user_hint=f"Git {operation} failed unexpectedly.",
                details={"operation": operation, "error": str(e)},
            )
