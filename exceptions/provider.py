#!/usr/bin/env python3
"""
Provider Exception Classes
==========================

Provider-specific exception classes for proper error handling
in the multi-provider architecture.
"""

from typing import Optional
from .base import MonkBaseError


class ProviderError(MonkBaseError):
    """
    Base exception for all provider-related errors.
    
    This is the parent class for all provider-specific exceptions
    and provides common functionality for provider error handling.
    """
    
    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        
        # Add provider-specific details if not already present
        if "provider_name" not in self.details and provider_name:
            self.details["provider_name"] = provider_name
        if "model_name" not in self.details and model_name:
            self.details["model_name"] = model_name


class ProviderNotAvailableError(ProviderError):
    """
    Raised when a provider is unavailable or fails to respond.
    
    This exception is used when a provider cannot be contacted,
    returns errors, or is otherwise unavailable for use.
    """
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, **kwargs)
        self.user_hint = (
            "The LLM provider is currently unavailable. "
            "Please check your internet connection, API keys, or try again later."
        )


class ProviderConfigurationError(ProviderError):
    """
    Raised when provider configuration is invalid or missing.
    
    This exception is used when provider settings are malformed,
    required configuration is missing, or values are out of valid ranges.
    """
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, **kwargs)
        self.user_hint = (
            "The provider configuration is invalid. "
            "Please check your configuration files and environment variables."
        )


class ProviderAuthenticationError(ProviderError):
    """
    Raised when provider authentication fails.
    
    This exception is used when API keys are invalid, expired,
    or authentication otherwise fails.
    """
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, **kwargs)
        self.user_hint = (
            "Authentication with the provider failed. "
            "Please check your API keys and authentication settings."
        )


class ProviderRateLimitError(ProviderError):
    """
    Raised when provider rate limits are exceeded.
    
    This exception includes retry information and guidance
    for handling rate limiting scenarios.
    """
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        limit_type: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        
        # Add rate limit specific details
        if retry_after is not None:
            self.details["retry_after_seconds"] = retry_after
        if limit_type:
            self.details["limit_type"] = limit_type
        
        # Provide user-friendly guidance
        if retry_after:
            self.user_hint = (
                f"Rate limit exceeded. Please wait {retry_after} seconds before trying again."
            )
        else:
            self.user_hint = (
                "Rate limit exceeded. Please wait before making additional requests."
            )


class ProviderModelNotSupportedError(ProviderError):
    """
    Raised when a provider does not support the requested model.
    
    This exception is used when a model name is not available
    or supported by a specific provider.
    """
    
    def __init__(self, message: str, supported_models: Optional[list] = None, **kwargs):
        super().__init__(message, **kwargs)
        
        if supported_models:
            self.details["supported_models"] = supported_models
        
        self.user_hint = (
            "The requested model is not supported by this provider. "
            "Please check available models or try a different provider."
        )


class ProviderConnectionError(ProviderError):
    """
    Raised when provider connection fails.
    
    This exception is used for network-related issues,
        """
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, **kwargs)
        self.user_hint = (
            "Failed to connect to the provider. "
            "Please check your internet connection and provider status."
        )


class ProviderResponseError(ProviderError):
    """
    Raised when provider response is invalid or malformed.
    
    This exception is used when the provider returns data
    that cannot be parsed or is in an unexpected format.
    """
    
    def __init__(self, message: str, response_data: Optional[dict] = None, **kwargs):
        super().__init__(message, **kwargs)
        
        if response_data:
            self.details["response_data"] = response_data
        
        self.user_hint = (
            "The provider returned an invalid response. "
            "This may be a temporary issue or provider API change."
        )
