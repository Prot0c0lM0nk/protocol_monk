#!/usr/bin/env python3
"""
Provider Package
================

Package containing all provider implementations for the multi-provider architecture.

Each provider implements the BaseModelClient interface and provides
provider-specific functionality while maintaining API compatibility.
"""
# Import provider classes for easy access
from .ollama_model_client_sdk import OllamaModelClientSDK
from .openrouter_model_client_sdk import OpenRouterModelClient

__all__ = [
    "OllamaModelClientSDK",
    "OpenRouterModelClient",
]
