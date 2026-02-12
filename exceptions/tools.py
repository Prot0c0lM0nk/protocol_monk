#!/usr/bin/env python3
"""
Tool Exception Definitions for MonkCode

All tool-related exceptions inherit from MonkBaseError.
"""

from exceptions.base import MonkBaseError


class ToolError(MonkBaseError):
    """Base exception for tool-related errors."""

    def __init__(self, message, tool_name=None, **kwargs):
        super().__init__(message, **kwargs)
        self.tool_name = tool_name
        if tool_name and "tool_name" not in self.details:
            self.details["tool_name"] = tool_name


class ToolExecutionError(ToolError):
    """Raised when tool execution fails."""

    def __init__(self, message, tool_name=None, **kwargs):
        super().__init__(message, tool_name=tool_name, **kwargs)


class ToolSecurityError(ToolError):
    """Raised when tool execution is blocked by security policy."""

    def __init__(self, message, tool_name=None, security_reason=None, **kwargs):
        super().__init__(message, tool_name=tool_name, **kwargs)
        self.security_reason = security_reason
        if security_reason and "security_reason" not in self.details:
            self.details["security_reason"] = security_reason


class ToolNotFoundError(ToolError):
    """Raised when requested tool is not found in registry."""

    def __init__(self, message, tool_name=None, **kwargs):
        super().__init__(message, tool_name=tool_name, **kwargs)


class UserCancellationError(ToolError):
    """Raised when user cancels an operation, typically by rejecting a tool call."""

    def __init__(self, message="Operation cancelled by user", **kwargs):
        super().__init__(message, **kwargs)


class ToolRegistryError(ToolError):
    """Raised when tool registry initialization or operations fail."""

    pass


class ToolInputValidationError(ToolError):
    """Raised when tool input parameters fail validation."""

    def __init__(self, message, tool_name=None, invalid_input=None, **kwargs):
        super().__init__(message, tool_name=tool_name, **kwargs)
        self.invalid_input = invalid_input
        if invalid_input is not None and "invalid_input" not in self.details:
            self.details["invalid_input"] = invalid_input
