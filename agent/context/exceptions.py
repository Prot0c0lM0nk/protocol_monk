from agent.exceptions import MonkBaseError

class ContextError(MonkBaseError):
    """Base exception for context management errors."""
    pass

class ContextOverflowError(ContextError):
    """Raised when context token limit is exceeded."""
    def __init__(self, message, current_tokens=None, max_tokens=None):
        super().__init__(message)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens

class ContextCorruptionError(ContextError):
    """Raised when context data structure is corrupted."""
    def __init__(self, message, corruption_type=None):
        super().__init__(message)
        self.corruption_type = corruption_type
