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
