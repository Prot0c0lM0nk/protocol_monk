#!/usr/bin/env python3
"""
OpenRouter Model Client Provider (Official SDK Version)
======================================================

OpenRouter-specific implementation using the official OpenRouter SDK.
This provides native OpenRouter API access with full feature support.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

# Import the official OpenRouter SDK
from openrouter import OpenRouter

from agent.base_model_client import BaseModelClient
from config.static import settings
from exceptions import (
    EmptyResponseError,
    ModelError,
    ModelTimeoutError,
    ProviderAuthenticationError,
)


class OpenRouterModelClient(BaseModelClient):
    """
    OpenRouter-specific implementation using the official OpenRouter SDK.

    This provider allows access to multiple LLM models through the OpenRouter API
    using the native SDK for better reliability and feature support.
    """

    def __init__(self, model_name: str, provider_config: Optional[Dict] = None):
        """
        Initialize the OpenRouter model client.

        Args:
            model_name: LLM model identifier (e.g., "anthropic/claude-3-sonnet")
            provider_config: Provider-specific configuration
        """
        # Initialize base class with default config
        if provider_config is None:
            provider_config = {
                "timeout": 420,
                "max_retries": 3,
                "retry_delay": 1.0,
            }

        super().__init__(model_name, provider_config)

        # Get OpenRouter API key from settings
        self.api_key = settings.environment.openrouter_api_key
        if not self.api_key:
            raise ProviderAuthenticationError(
                "OpenRouter API key not found in settings. Set OPENROUTER_API_KEY environment variable.",
                provider_name="openrouter",
            )

        # Initialize the OpenRouter client
        self.client = OpenRouter(
            api_key=self.api_key,
            # The OpenRouter SDK doesn't accept timeout in constructor
            # We'll handle timeout at the request level instead
        )

        # Model options (temperature, etc.)
        self.model_options = {
            "temperature": 0.7,
            "max_tokens": 4096,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }

    async def get_response_async(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Union[str, Dict], None]:
        """
        Get response from OpenRouter using the official SDK.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to stream the response (default: True)
            tools: Optional list of tool definitions

        Yields:
            str: Content chunks from the response
            Dict: Tool call responses (when tools are invoked)

        Raises:
            ModelError: For provider errors
            ModelTimeoutError: For timeouts
            EmptyResponseError: For empty responses
        """
        try:
            # Prepare messages
            messages = conversation_context

            # Build request parameters
            request_params = {
                "model": self.model_name,
                "messages": messages,
                "stream": stream,
                **self.model_options,
            }

            # Add tools if provided
            if tools:
                request_params["tools"] = tools

            self.logger.info(
                "Making OpenRouter request to model: %s (stream=%s)",
                self.model_name,
                stream,
            )

            if stream:
                # Streaming response using official SDK
                # The SDK doesn't have native async streaming, so we'll use a hybrid approach
                # We'll process the stream synchronously but yield results asynchronously
                
                response = self.client.chat.send(**request_params)
                
                # Process streaming in small batches to avoid blocking
                loop = asyncio.get_event_loop()
                
                def get_next_event(iterator):
                    """Get next event from iterator"""
                    try:
                        return next(iterator), False
                    except StopIteration:
                        return None, True
                
                # Create iterator from response
                response_iter = iter(response)
                
                # Process events asynchronously
                while True:
                    # Get next event in thread pool to avoid blocking
                    event, done = await loop.run_in_executor(None, get_next_event, response_iter)
                    
                    if done:
                        break
                    
                    if not event.choices:
                        continue

                    delta = event.choices[0].delta

                    # Check for content
                    if delta.content:
                        self.logger.debug(f"Yielding content: {delta.content[:50]}...")
                        yield delta.content

                    # Check for tool calls
                    if delta.tool_calls:
                        # Convert tool calls to our format
                        tool_calls = []
                        for tc in delta.tool_calls:
                            tc_data = {
                                "index": getattr(tc, 'index', 0),
                                "id": getattr(tc, 'id', ''),
                                "type": "function",
                                "function": {},
                            }

                            # Handle function fields if present
                            if hasattr(tc, 'function') and tc.function:
                                if hasattr(tc.function, 'name') and tc.function.name:
                                    tc_data["function"]["name"] = tc.function.name
                                if hasattr(tc.function, 'arguments') and tc.function.arguments:
                                    tc_data["function"]["arguments"] = tc.function.arguments

                            tool_calls.append(tc_data)

                        self.logger.debug(f"Yielding tool_calls: {tool_calls}")
                        yield {"tool_calls": tool_calls}
            else:
                # Non-streaming response using official SDK
                response = await self.client.chat.send_async(**request_params)
                
                # Extract content
                content = response.choices[0].message.content
                if content:
                    yield content

                # Extract tool calls (non-streaming)
                message = response.choices[0].message
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    tool_calls = []
                    for tc in message.tool_calls:
                        tool_calls.append({
                            "id": getattr(tc, 'id', ''),
                            "type": "function",
                            "function": {
                                "name": getattr(tc.function, 'name', ''),
                                "arguments": getattr(tc.function, 'arguments', ''),
                            },
                        })
                    yield {"tool_calls": tool_calls}

                if not content and (not hasattr(message, 'tool_calls') or not message.tool_calls):
                    raise EmptyResponseError(
                        message="Model returned an empty response",
                        details={"provider": "openrouter", "model": self.model_name},
                    )
        except asyncio.TimeoutError as exc:
            raise ModelTimeoutError(
                message="Model request timed out",
                timeout_seconds=self.timeout,
                details={"provider": "openrouter", "model": self.model_name},
            ) from exc
        except Exception as e:
            # Check for authentication errors
            error_msg = str(e).lower()
            if "authentication" in error_msg or "unauthorized" in error_msg or "api key" in error_msg:
                raise ProviderAuthenticationError(
                    f"OpenRouter authentication failed: {str(e)}",
                    provider_name="openrouter",
                ) from e

            # Check for rate limiting
            if "rate limit" in error_msg or "too many requests" in error_msg:
                raise ModelError(
                    message=f"OpenRouter rate limit exceeded: {str(e)}",
                    details={"provider": "openrouter", "model": self.model_name},
                ) from e

            # Check for content errors
            if "content" in error_msg and "messages" in error_msg:
                self.logger.error(f"Content format error: {str(e)}")

            # Generic error
            raise ModelError(
                message=f"OpenRouter error: {str(e)}",
                details={"provider": "openrouter", "model": self.model_name},
            ) from e

    async def close(self) -> None:
        """
        Clean up resources (close the OpenRouter client).
        """
        # The OpenRouter SDK handles cleanup automatically when used as context manager
        # But we can explicitly close if needed
        if hasattr(self.client, 'close'):
            await self.client.close()

    def _prepare_payload(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare request payload for OpenRouter.

        Note: This method is kept for compatibility with BaseModelClient,
        but the actual request is made using the OpenRouter SDK.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to enable streaming
            tools: Optional tool definitions

        Returns:
            Dict[str, Any]: Request payload
        """
        payload = {
            "model": self.model_name,
            "messages": conversation_context,
            "stream": stream,
            **self.model_options,
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _extract_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract content from response data.

        Note: This method is kept for compatibility with BaseModelClient,
        but the actual content extraction is done by the OpenRouter SDK.

        Args:
            response_data: Response data dictionary

        Returns:
            Optional[str]: Extracted content or None if error
        """
        if "choices" in response_data and response_data["choices"]:
            return response_data["choices"][0]["message"]["content"]
        return None

    def supports_tools(self) -> bool:
        """
        Return True if provider supports tool/function calling.

        Returns:
            bool: OpenRouter supports tools via OpenAI-compatible API
        """
        return True
