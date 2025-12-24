#!/usr/bin/env python3
"""
Model Client Compatibility Wrapper
===================================

Backward compatibility wrapper that maintains exact same interface as before
while delegating to the new provider registry system.

This ensures zero breaking changes for existing code.
"""

import warnings
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from textual.containers import Container
from textual.widgets import Static, Markdown

from agent.base_model_client import BaseModelClient
from agent.provider_registry import ProviderRegistry
from agent.providers.ollama_model_client import OllamaModelClient
from agent.providers.openrouter_model_client import OpenRouterModelClient
from config.static import settings
from exceptions import (
    EmptyResponseError,
    ModelError,
    ModelTimeoutError,
    ProviderError,
    ProviderNotAvailableError,
)


class ModelClient:
    """
    Backward compatibility wrapper for the multi-provider architecture.

    Maintains exact same interface as the original ModelClient while
    using the new ProviderRegistry internally for provider management
    and failover capabilities.

    This class ensures that all existing code continues to work without
    any changes, while gaining the benefits of the multi-provider system.
    """

    def __init__(self, model_name: str, provider: Optional[str] = None):
        """
        Initialize the model client with explicit provider selection.

        Args:
            model_name: LLM model identifier (e.g., "qwen3:4b")
            provider: Provider name ("ollama", "openrouter", or None for auto-detection)
        """
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)

        # Determine provider
        if provider:
            self.selected_provider = provider
        else:
            self.selected_provider = self._detect_provider(model_name)

        self.logger.info(f"Using provider: {self.selected_provider}")

        # Create provider-specific client
        self._client = self._create_provider_client(self.selected_provider, model_name)
        self.current_provider = self.selected_provider  # Backward compatibility

    def _detect_provider(self, model_name: str) -> str:
        """
        Auto-detect provider based on model name patterns.

        Args:
            model_name: Name of the model

        Returns:
            str: Detected provider name
        """
        # Check for OpenRouter patterns
        if "/" in model_name or any(
            x in model_name.lower()
            for x in ["gpt", "claude", "gemini", "anthropic", "meta-llama"]
        ):
            return "openrouter"

        # Default to Ollama for local models AND Ollama cloud models
        return "ollama"

    def _create_provider_client(
        self, provider: str, model_name: str
    ) -> BaseModelClient:
        """
        Create provider-specific client.

        Args:
            provider: Provider name
            model_name: Model name

        Returns:
            BaseModelClient: Provider client instance
        """
        if provider == "ollama":
            return OllamaModelClient(model_name)
        elif provider == "openrouter":
            return OpenRouterModelClient(model_name)
        else:
            raise ValueError(
                f"Unknown provider: {provider}. Available: ollama, openrouter"
            )

    def switch_provider(self, provider: str) -> None:
        """
        Switch to a different provider (user-controlled).

        Args:
            provider: New provider name ("ollama" or "openrouter")
        """
        self.logger.info(
            f"Switching provider from {self.selected_provider} to {provider}"
        )
        self.selected_provider = provider
        self._client = self._create_provider_client(provider, self.model_name)
        self.current_provider = provider  # Backward compatibility

    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get current provider information for status display.

        Returns:
            Dict[str, Any]: Provider information including name and capabilities
        """
        return {
            "provider_name": self.current_provider,
            "model_name": self.model_name,
            "supports_streaming": True,  # Both providers support streaming
            "supports_tools": self._client.supports_tools() if self._client else False,
        }

    async def get_response_async(
        self, conversation_context: List[Dict], stream: bool = True, tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Union[str, Dict], None]:
        """
        Async generator that yields response chunks from the model.

        Args:
            conversation_context: List of conversation messages for the model
            stream: Whether to stream the response (default: True)

        Yields:
            str: Response content chunks from the model

        Raises:
            EmptyResponseError: If model returns empty response (non-streaming)
            ModelTimeoutError: If request times out
            ModelError: If connection or API error occurs
        """
        if not self._client:
            raise ModelError(
                "Model client not initialized",
                details={"model": self.model_name, "provider": self.current_provider},
            )

        # Direct delegation to provider - no failover, user-controlled
        async for chunk in self._client.get_response_async(
            conversation_context, stream, tools
        ):
            yield chunk

    def set_model(self, model_name: str) -> None:
        """
        Switch to a different model and update context window in options.

        Args:
            model_name: Name of the model to switch to
        """
        self.logger.info(f"ModelClient: Switching model from {self.model_name} to {model_name}")
        self.model_name = model_name

        # Re-initialize client for new model with same provider
        self._client = self._create_provider_client(self.selected_provider, model_name)

        # For backward compatibility, also set on the client if it supports it
        if hasattr(self._client, "set_model"):
            self.logger.info(f"ModelClient: Calling set_model on provider client")
            self._client.set_model(model_name)
        else:
            self.logger.info(f"ModelClient: Provider client does not have set_model method, created new instance")

        self.logger.info(f"ModelClient: Model switched to {self.model_name}")
    async def close(self) -> None:
        """
        Close the model client and clean up resources.
        """
        if self._client:
            await self._client.close()
        # No registry to close - using direct provider creation for user-controlled switching

    def get_response(self, conversation_context: List[Dict], stream: bool = True):
        """
        Synchronous generator for backward compatibility.

        WARNING: This method exists only for backward compatibility. It will:
        - Block the current thread while waiting for responses
        - May cause UI freezes in GUI applications
        - Should be avoided in favor of get_response_async()

        For GUI applications, use get_response_async() with proper async/await patterns.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to stream the response (default: True)

        Yields:
            str: Response content chunks

        Raises:
            RuntimeError: If called from within an existing event loop
            ModelError: If the model request fails
        """
        warnings.warn(
            "get_response() is deprecated and may block the event loop. "
            "Use get_response_async() instead for better performance and reliability.",
            DeprecationWarning,
            stacklevel=2,
        )

        import asyncio

        # Check if we're already in an event loop - prevent nested loop corruption
        try:
            existing_loop = asyncio.get_running_loop()
            raise RuntimeError(
                "get_response() cannot be called from within an existing event loop. "
                "Use get_response_async() instead, or call this method from a different thread."
            )
        except RuntimeError as e:
            # This is expected - we're not in a loop
            if "no running event loop" not in str(e).lower():
                raise

        # Use asyncio.run() for proper event loop lifecycle management
        # This approach works well with the buffering system that processes
        # complete tool calls before yielding
        async def _collect_all_chunks():
            """Collect all chunks from the async generator"""
            chunks = []
            async for chunk in self.get_response_async(conversation_context, stream):
                chunks.append(chunk)
            return chunks

        try:
            # Run the async generator and collect all chunks
            all_chunks = asyncio.run(_collect_all_chunks())
            for chunk in all_chunks:
                yield chunk
        except Exception as e:
            self.logger.error(f"Error in get_response: {e}")
            raise ModelError(f"Failed to get model response: {e}") from e

    # Backward compatibility properties and methods

    @property
    def ollama_url(self) -> str:
        """
        Get the Ollama URL for backward compatibility.

        Returns:
            str: Ollama URL from settings
        """
        return settings.api.ollama_url

    @property
    def timeout(self) -> int:
        """
        Get the timeout for backward compatibility.

        Returns:
            int: Timeout value from client or default
        """
        if self._client:
            return getattr(self._client, "timeout", 420)
        return settings.api.provider_timeout

    @property
    def model_options(self) -> Dict[str, Any]:
        """
        Get model options for backward compatibility.

        Returns:
            Dict[str, Any]: Model options from client or default
        """
        if self._client and hasattr(self._client, "model_options"):
            return self._client.model_options
        return settings.model_options.chat_options

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get model information for backward compatibility.

        Returns:
            Dict[str, Any]: Model information
        """
        if self._client:
            return self._client.get_model_info()

        return {
            "model_name": self.model_name,
            "provider_name": self.current_provider,
            "timeout": self.timeout,
        }
