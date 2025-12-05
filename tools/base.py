"""
Base classes and interfaces for the tool system.
"""

from enum import Enum
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Handle fallback for constants
try:
    if __package__:
        from ._constants import DANGEROUS_FILE_PATTERNS
    else:
        from _constants import DANGEROUS_FILE_PATTERNS
except ImportError:
    DANGEROUS_FILE_PATTERNS = ["/etc/", ".ssh/", "../", ".env", ".git/"]


@dataclass
class ToolSchema:
    """Describes a tool's interface."""

    name: str
    description: str
    parameters: Dict[str, Any]
    required_params: List[str]


class ExecutionStatus(Enum):
    """Enumeration of possible tool execution statuses."""

    SUCCESS = "success"
    INVALID_PARAMS = "invalid_params"
    SECURITY_BLOCKED = "security_blocked"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    EXTERNAL_ERROR = "external_error"
    INTERNAL_ERROR = "internal_error"


class ToolResult:
    """Standardized result from tool execution."""

    def __init__(self, status_or_success, output: str, data: Dict = None):
        if isinstance(status_or_success, bool):
            self.status = (
                ExecutionStatus.SUCCESS
                if status_or_success
                else ExecutionStatus.INTERNAL_ERROR
            )
        else:
            self.status = status_or_success

        self.output = output
        self.data = data or {}
        self.success = self.status in (
            ExecutionStatus.SUCCESS,
            ExecutionStatus.COMMAND_FAILED,
        )

    @classmethod
    def success_result(cls, output: str, data: Dict = None):
        """Create a successful execution result."""
        return cls(ExecutionStatus.SUCCESS, output, data)

    @classmethod
    def command_failed(cls, output: str, exit_code: int):
        """Create a result for a failed command execution."""
        return cls(ExecutionStatus.COMMAND_FAILED, output, {"exit_code": exit_code})

    @classmethod
    def invalid_params(cls, output: str, missing_params: list = None):
        """Create a result for invalid parameters."""
        return cls(ExecutionStatus.INVALID_PARAMS, output, {"missing": missing_params})

    @classmethod
    def security_blocked(cls, reason: str):
        """Create a result for a security block."""
        return cls(
            ExecutionStatus.SECURITY_BLOCKED,
            f"Security Blocked: {reason}",
            {"reason": reason},
        )

    @classmethod
    def internal_error(cls, output: str):
        """Create a result for an internal error."""
        return cls(ExecutionStatus.INTERNAL_ERROR, output)

    @classmethod
    def timeout(cls, output: str):
        """Create a result for an execution timeout."""
        return cls(ExecutionStatus.TIMEOUT, output)


class BaseTool(ABC):
    """Abstract base class for all tools."""

    def __init__(self, working_dir: Path):
        self.logger = logging.getLogger(f"tools.{self.__class__.__name__}")
        self.working_dir = Path(working_dir).resolve()

        # Ensure working directory exists
        if not self.working_dir.exists():
            try:
                self.working_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise OSError(f"Could not create working directory: {e}") from e

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool's schema definition."""

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool's main logic."""

    def _is_safe_file_path(self, filepath: str) -> bool:
        """
        Check if file path is within working directory and not dangerous.

        Args:
            filepath: The path to validate.

        Returns:
            bool: True if safe, False otherwise.
        """
        try:
            path_obj = Path(filepath)

            # Logic Change: Determine if we join or resolve directly
            if path_obj.is_absolute():
                # If it's absolute, we check it directly
                target_path = path_obj.resolve()
            else:
                # If relative, we join, but first we check if the user
                # accidently provided a path that implies the working dir
                # (e.g. "path/to/cwd/file.txt") to prevent duplication.
                str_path = str(filepath)
                str_cwd = str(self.working_dir)

                # Remove leading slash/cwd if duplicates the cwd
                if str_path.startswith(str_cwd):
                    str_path = str_path[len(str_cwd) :].lstrip(os.sep)

                target_path = (self.working_dir / str_path).resolve()

            # 1. Path Traversal Check
            if not str(target_path).startswith(str(self.working_dir)):
                self.logger.warning(
                    "Security: Path traversal blocked: %s -> %s", filepath, target_path
                )
                return False

            # 2. Dangerous Pattern Check
            path_str = str(target_path)
            for pattern in DANGEROUS_FILE_PATTERNS:
                if pattern in path_str:
                    self.logger.warning(
                        "Security: Dangerous pattern '%s' blocked in %s",
                        pattern,
                        filepath,
                    )
                    return False

            return True

        except (OSError, ValueError) as e:
            self.logger.error("Path validation error: %s", e)
            return False
