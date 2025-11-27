from agent.exceptions import MonkBaseError

class ModelError(MonkBaseError):
    """Base exception for model-related errors."""
    pass

class ModelTimeoutError(ModelError):
    """Raised when model API request times out."""
    def __init__(self, message, timeout_seconds=None):
        super().__init__(message)
        self.timeout_seconds = timeout_seconds

class ModelConfigurationError(ModelError):
    """Raised when model configuration is invalid or missing."""
    pass

class EmptyResponseError(ModelError):
    """Raised when model returns an empty response."""
    pass
