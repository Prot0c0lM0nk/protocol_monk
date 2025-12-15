#!/usr/bin/env python3
"""
Base Model Client Interface
==========================

Abstract base class defining the provider interface that all LLM providers must implement.
Ensures consistent API across providers while maintaining backward compatibility.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from exceptions import (
    EmptyResponseError,
    ModelError,
    ModelTimeoutError,
)


class BaseModelClient(ABC):
    """
    Abstract base class that defines the contract for all LLM providers.

    All provider implementations must inherit from this class and implement
    the abstract methods. This ensures consistent API across all providers
    while maintaining backward compatibility with existing code.
    """

    def __init__(
        self, model_name: str, provider_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the base model client.

        Args:
            model_name: The model identifier (e.g., "gpt-4", "qwen3:4b")
            provider_config: Provider-specific configuration
        """
        self.model_name = model_name
        self.provider_config = provider_config or {}
        self.logger = logging.getLogger(__name__)

        # Default timeout and retry settings (can be overridden by provider config)
        self.timeout = self.provider_config.get("timeout", 420)
        self.max_retries = self.provider_config.get("max_retries", 3)
        self.retry_delay = self.provider_config.get("retry_delay", 1.0)

    @abstractmethod
    async def get_response_async(
        self, conversation_context: List[Dict[str, str]], stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Core method that yields response chunks from the model.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to stream the response (default: True)

        Yields:
            str: Content chunks from the response

        Raises:
            ModelError: For provider errors
            ModelTimeoutError: For timeouts
            EmptyResponseError: For empty responses
        """
        pass

    @abstractmethod
    def _prepare_payload(
        self, conversation_context: List[Dict[str, str]], stream: bool
    ) -> Dict[str, Any]:
        """
        Convert generic conversation format to provider-specific request payload.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to enable streaming

        Returns:
            Dict[str, Any]: Provider-specific request payload
        """
        pass

    @abstractmethod
    def _extract_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract text content from provider-specific response format.

        Args:
            response_data: Provider-specific response data

        Returns:
            Optional[str]: Extracted content or None if invalid
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Clean up resources (HTTP sessions, connections, etc.).
        """
        pass

    # Concrete methods with common implementation

    def get_model_info(self) -> Dict[str, Any]:
        """
        Return model information including name, provider type, and settings.

        Returns:
            Dict[str, Any]: Model information dictionary
        """
        return {
            "model_name": self.model_name,
            "provider_name": self.get_provider_name(),
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "supports_tools": self.supports_tools(),
            "supports_streaming": True,  # Default assumption
        }

    def supports_tools(self) -> bool:
        """
        Return True if provider supports tool/function calling.

        Default implementation returns False. Override in provider classes.

        Returns:
            bool: Whether provider supports tools
        """
        return False

    def get_provider_name(self) -> str:
        """
        Return provider name based on class name.

        Returns:
            str: Provider name (e.g., "ollama", "openrouter")
        """
        class_name = self.__class__.__name__.lower()
        # Remove "modelclient" suffix if present
        if class_name.endswith("modelclient"):
            class_name = class_name[:-11]
        return class_name

    async def _execute_with_retry(self, func, *args, **kwargs) -> Any:
        """
        Execute function with exponential backoff retry logic.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Any: Function result

        Raises:
            Exception: Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except (ModelError, ModelTimeoutError) as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2**attempt)  # Exponential backoff
                    self.logger.warning(
                        f"Provider error (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"Provider failed after {self.max_retries + 1} attempts: {e}"
                    )
                    raise
            except Exception as e:
                # Don't retry on unexpected errors
                raise e

        raise last_exception
