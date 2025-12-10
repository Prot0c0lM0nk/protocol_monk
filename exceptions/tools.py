#!/usr/bin/env python3
"""
Tool Exception Definitions for MonkCode

All tool-related exceptions inherit from MonkBaseError.
"""

from exceptions.base import MonkBaseError


class ToolError(MonkBaseError):
    """Base exception for tool-related errors."""

    pass


class ToolExecutionError(ToolError):
    """Raised when tool execution fails."""

    def __init__(self, message, tool_name=None):
        super().__init__(message)
        self.tool_name = tool_name


class ToolSecurityError(ToolError):
    """Raised when tool execution is blocked by security policy."""

    def __init__(self, message, tool_name=None, security_reason=None):
        super().__init__(message)
        self.tool_name = tool_name
        self.security_reason = security_reason


class ToolNotFoundError(ToolError):
    """Raised when requested tool is not found in registry."""

    def __init__(self, message, tool_name=None):
        super().__init__(message)
        self.tool_name = tool_name


class UserCancellationError(ToolError):
    """Raised when user cancels an operation, typically by rejecting a tool call."""

    def __init__(self, message="Operation cancelled by user"):
        super().__init__(message)
class ToolRegistryError(ToolError):
    """Raised when tool registry initialization or operations fail."""
    pass



class ToolInputValidationError(ToolError):
    """Raised when tool input parameters fail validation."""
    
    def __init__(self, message, tool_name=None, invalid_input=None):
        super().__init__(message)
        self.tool_name = tool_name
        self.invalid_input = invalid_input