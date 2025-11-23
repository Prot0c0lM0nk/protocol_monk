import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from agent import exceptions

# Handle fallback for constants
try:
    if __package__:
        from ._constants import DANGEROUS_FILE_PATTERNS
    else:
        from _constants import DANGEROUS_FILE_PATTERNS
except ImportError:
    DANGEROUS_FILE_PATTERNS = ['/etc/', '.ssh/', '../', '.env', '.git/']

@dataclass
class ToolSchema:
    """Describes a tool's interface."""
    name: str
    description: str
    parameters: Dict[str, Any]
    required_params: list[str]

class ExecutionStatus(Enum):
    SUCCESS = "success"
    INVALID_PARAMS = "invalid_params"
    SECURITY_BLOCKED = "security_blocked"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    EXTERNAL_ERROR = "external_error"
    INTERNAL_ERROR = "internal_error"

class ToolResult:
    """Standardized result from tool execution."""
    def __init__(self, status_or_success, output: str, data: Dict = None, **kwargs):
        if isinstance(status_or_success, bool):
            self.status = ExecutionStatus.SUCCESS if status_or_success else ExecutionStatus.INTERNAL_ERROR
        else:
            self.status = status_or_success
        
        self.output = output
        self.data = data or {}
        self.success = self.status in (ExecutionStatus.SUCCESS, ExecutionStatus.COMMAND_FAILED)

    @classmethod
    def success_result(cls, output: str, data: Dict = None):
        return cls(ExecutionStatus.SUCCESS, output, data)

    @classmethod
    def command_failed(cls, output: str, exit_code: int):
        return cls(ExecutionStatus.COMMAND_FAILED, output, {"exit_code": exit_code})

    @classmethod
    def invalid_params(cls, output: str, missing_params: list = None):
        return cls(ExecutionStatus.INVALID_PARAMS, output, {"missing": missing_params})

    @classmethod
    def security_blocked(cls, reason: str):
        return cls(ExecutionStatus.SECURITY_BLOCKED, f"Security Blocked: {reason}", {"reason": reason})

    @classmethod
    def internal_error(cls, output: str):
        return cls(ExecutionStatus.INTERNAL_ERROR, output)

    @classmethod
    def timeout(cls, output: str):
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
            except Exception as e:
                raise exceptions.ConfigurationError(f"Could not create working directory: {e}")

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        pass

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        pass

    def _is_safe_file_path(self, filepath: str, read_only: bool = False) -> bool:
        """
        Check if file path is within working directory and not dangerous.
        """
        try:
            # Resolve path relative to working dir
            target_path = (self.working_dir / filepath).resolve()
            
            # 1. Path Traversal Check
            if not str(target_path).startswith(str(self.working_dir)):
                self.logger.warning(f"Security: Path traversal blocked: {filepath}")
                return False
            
            # 2. Dangerous Pattern Check
            path_str = str(target_path)
            for pattern in DANGEROUS_FILE_PATTERNS:
                if pattern in path_str:
                    self.logger.warning(f"Security: Dangerous pattern '{pattern}' blocked in {filepath}")
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Path validation error: {e}")
            return False