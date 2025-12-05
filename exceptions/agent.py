#!/usr/bin/env python3
"""
Agent Exception Definitions for MonkCode

Agent-level exceptions that don't fit in other categories.
"""

from pathlib import Path

from exceptions.base import MonkBaseError
"""
Agent Exception Definitions for MonkCode

Agent-level exceptions that don't fit in other categories.
"""

from exceptions.base import MonkBaseError


class AgentError(MonkBaseError):
    """Base exception for agent-level errors."""

    pass


class ConfigurationError(AgentError):
    """Raised when agent configuration is invalid or missing."""

    pass



class OrchestrationError(AgentError):
    """Raised when orchestration logic fails."""

    pass



class ScratchManagerError(AgentError):
    """Raised when scratch file operations fail."""

    def __init__(
        self,
        message: str,
        operation: str = None,
        scratch_id: str = None,
        file_path: Path = None,
        original_error: Exception = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.scratch_id = scratch_id
        self.file_path = file_path
        self.original_error = original_error
