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

# Agent exceptions
from .agent import (
    AgentError,
    ConfigurationError,
    OrchestrationError,
    ScratchManagerError,
)

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
    
    # Agent
    "AgentError",
    "ConfigurationError",
    "OrchestrationError",
    "ScratchManagerError",
]
