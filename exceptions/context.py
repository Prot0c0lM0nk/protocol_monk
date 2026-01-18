from .base import MonkBaseError


class ContextError(MonkBaseError):
    """
    State management or token limit errors.

    Used when:
    - Context limits are exceeded and pruning fails.
    - Message history is corrupted.
    """

    pass
