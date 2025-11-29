from agent.exceptions import MonkBaseError


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
