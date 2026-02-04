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
    ModelResponseParseError,
    ModelRateLimitError,
)

# Provider exceptions
from .provider import (
    ProviderError,
    ProviderNotAvailableError,
    ProviderConfigurationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderModelNotSupportedError,
    ProviderConnectionError,
    ProviderResponseError,
)

# Tool exceptions
from .tools import (
    ToolError,
    ToolExecutionError,
    ToolInputValidationError,
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
    SessionInitializationError,
    UIInitializationError,
    ToolRegistryError,
    ModelClientError,
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
    "ModelResponseParseError",
    "ModelRateLimitError",
    # Tool
    "ToolError",
    "ToolExecutionError",
    "ToolInputValidationError",
    "ToolSecurityError",
    "ToolNotFoundError",
    "UserCancellationError",
    # Context
    "ContextError",
    "ContextOverflowError",
    "ContextCorruptionError",
    "ContextValidationError",
    "TokenEstimationError",
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
    # Provider
    "ProviderError",
    "ProviderNotAvailableError",
    "ProviderConfigurationError",
    "ProviderAuthenticationError",
    "ProviderRateLimitError",
    "ProviderModelNotSupportedError",
    "ProviderConnectionError",
    "ProviderResponseError",
]
