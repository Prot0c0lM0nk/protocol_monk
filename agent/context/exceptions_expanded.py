from agent.context.exceptions import ContextError
from agent.core_exceptions import AgentCoreError
from pathlib import Path
from typing import Any, Optional


class TokenEstimationError(ContextError):
    """Raised when token estimation fails due to estimator issues."""
    def __init__(self, message: str, estimator_name: str = None, failed_text: str = None, original_error: Exception = None):
        super().__init__(message)
        self.estimator_name = estimator_name
        self.failed_text = failed_text
        self.original_error = original_error


class NeuralSymIntegrationError(ContextError):
    """Raised when NeuralSym enhancement or recording fails."""
    def __init__(self, message: str, operation: str = None, model_name: str = None, original_error: Exception = None):
        super().__init__(message)
        self.operation = operation
        self.model_name = model_name
        self.original_error = original_error


class ContextValidationError(ContextError):
    """Raised when context validation fails."""
    def __init__(self, message: str, validation_type: str = None, invalid_value: Any = None):
        super().__init__(message)
        self.validation_type = validation_type
        self.invalid_value = invalid_value


class ScratchManagerError(AgentCoreError):
    """Raised when scratch file operations fail."""
    def __init__(self, message: str, operation: str = None, scratch_id: str = None, file_path: Path = None, original_error: Exception = None):
        super().__init__(message)
        self.operation = operation
        self.scratch_id = scratch_id
        self.file_path = file_path
        self.original_error = original_error
