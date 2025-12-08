#!/usr/bin/env python3
"""
MonkCode Exceptions Package

Unified exception hierarchy for the MonkCode agent.
"""

# Base exceptions
from .base import MonkBaseError, wrap_exception

# Model exceptions
from .model import (
    EmptyResponseError,
    ModelConfigurationError,
    ModelError,
    ModelTimeoutError,
)

# Tool exceptions
from .tools import (
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolSecurityError,
    UserCancellationError,
)

# Context exceptions
from .context import (
    ContextCorruptionError,
    ContextError,
    ContextOverflowError,
    ContextValidationError,
    NeuralSymIntegrationError,
    TokenEstimationError,
)

# Config exceptions
from .config import (
    ConfigFileError,
    DirectorySelectionError,
    ModelConfigError,
    ValidationError,
)

# Agent exceptions
from .agent import (
    AgentError,
    ConfigurationError,
    OrchestrationError,
    ScratchManagerError,
)

# Application/UI exceptions (new category for main.py)
class SessionInitializationError(MonkBaseError):
    """Raised when the application session fails to initialize."""
    pass

class UIInitializationError(MonkBaseError):
    """Raised when the user interface fails to initialize."""
    pass

class ToolRegistryError(MonkBaseError):
    """Raised for errors related to the tool registry."""
    pass

class ModelClientError(MonkBaseError):
    """Raised for errors related to the model client."""
    pass


__all__ = [
    # Base
    "MonkBaseError",
    "wrap_exception",
    
    # Model
    "ModelError",
    "ModelTimeoutError",
    "ModelConfigurationError",
    "EmptyResponseError",
    
    # Tool
    "ToolError",
    "ToolExecutionError",
    "ToolSecurityError",
    "ToolNotFoundError",
    "UserCancellationError",
    
    # Context
    "ContextError",
    "ContextOverflowError",
    "ContextCorruptionError",
    "ContextValidationError",
    "TokenEstimationError",
    "NeuralSymIntegrationError",
    
    # Config
    "ConfigFileError",
    "DirectorySelectionError",
    "ModelConfigError", 
    "ValidationError",
    
    # Agent
    "AgentError",
    "ConfigurationError",
    "OrchestrationError",
    "ScratchManagerError",
    
    # Application/UI
    "SessionInitializationError",
    "UIInitializationError", 
    "ToolRegistryError",
    "ModelClientError",
]