from .base import MonkBaseError


class ToolError(MonkBaseError):
    """
    Tool execution failures.

    Used when:
    - A file cannot be written (permissions).
    - A shell command fails (non-zero exit).
    - Arguments do not match schema.
    """

    pass


class ScratchManagerError(ToolError):
    """
    Raised when the ScratchManager fails to read or write temp files.
    """

    def __init__(self, message, operation=None, original_error=None, **kwargs):
        super().__init__(
            message,
            user_hint="I had trouble using my scratchpad memory.",
            details=kwargs,
        )
        self.operation = operation
        self.original_error = original_error
