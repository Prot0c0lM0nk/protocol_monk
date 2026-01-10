#!/usr/bin/env python3
"""
OpenRouter Model Client Provider (Official SDK Version)
======================================================

OpenRouter-specific implementation using the official OpenAI SDK.
OpenRouter is fully compatible with the OpenAI API format.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from openai import AsyncOpenAI

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
    OpenRouter-specific implementation using the official OpenAI SDK.

    This provider allows access to multiple LLM models through the OpenRouter API,
    supporting both streaming and non-streaming responses.
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

        # Get OpenRouter API key from settings (it's in environment.openrouter_api_key)
        self.api_key = settings.environment.openrouter_api_key
        if not self.api_key:
            raise ProviderAuthenticationError(
                "OpenRouter API key not found in settings. Set OPENROUTER_API_KEY environment variable.",
                provider_name="openrouter",
            )
        # Initialize the OpenAI client with OpenRouter's base URL
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=self.timeout,
            max_retries=self.max_retries,
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
        
        Note: This version assumes the conversation_context is strictly valid
        (Assistant Tool Calls MUST be followed by Tool Results).
        """
        try:
            # Prepare the request using OpenAI SDK format
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

            # DEBUG: Log the actual messages being sent
            self.logger.debug(f"DEBUG: Sending {len(messages)} messages to OpenRouter:")
            for i, msg in enumerate(messages):
                self.logger.debug(f"  messages[{i}]: role={msg.get('role')}, content={repr(msg.get('content'))}, tool_calls={'yes' if msg.get('tool_calls') else 'no'}")

            self.logger.info(
                "Making OpenRouter request to model: %s (stream=%s)",
                self.model_name,
                stream,
            )

            # Make the request
            if stream:
                # Streaming response
                stream_response = await self.client.chat.completions.create(
                    **request_params
                )
                
                self.logger.debug(f"Stream started for model: {self.model_name}")

                async for chunk in stream_response:
                    # Parse the Delta
                    if not chunk.choices:
                        continue
                        
                    delta = chunk.choices[0].delta
                    
                    # DEBUG: Log the raw chunk structure for visibility
                    self.logger.debug(f"Chunk ID: {chunk.id} | Content: {repr(delta.content)} | ToolCalls: {len(delta.tool_calls) if delta.tool_calls else 0}")

                    # 1. Check for content (INDEPENDENT CHECK)
                    if delta.content:
                        self.logger.debug(f"Yielding content: {delta.content[:50]}...")
                        yield delta.content

                    # 2. Check for tool calls (INDEPENDENT CHECK - NOT ELIF)
                    if delta.tool_calls:
                        # Convert tool calls to our format
                        tool_calls = []
                        for tc in delta.tool_calls:
                            # Safe extraction handling None values
                            tc_data = {
                                "index": tc.index,
                                "id": tc.id,
                                "type": "function",
                                "function": {}
                            }
                            
                            # Handle function fields if present
                            if tc.function:
                                if tc.function.name:
                                    tc_data["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tc_data["function"]["arguments"] = tc.function.arguments
                            
                            tool_calls.append(tc_data)
                        
                        self.logger.debug(f"Yielding tool_calls: {tool_calls}")
                        yield {"tool_calls": tool_calls}

            else:
                # Non-streaming response
                response = await self.client.chat.completions.create(
                    **request_params
                )

                # Extract content
                content = response.choices[0].message.content
                if content:
                    yield content
                
                # Extract tool calls (non-streaming)
                message = response.choices[0].message
                if message.tool_calls:
                    tool_calls = []
                    for tc in message.tool_calls:
                        tool_calls.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        })
                    yield {"tool_calls": tool_calls}
                    
                if not content and not message.tool_calls:
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
            # DEBUG: Log the full error details
            self.logger.error(f"DEBUG: OpenRouter error type: {type(e).__name__}")
            self.logger.error(f"DEBUG: OpenRouter error message: {str(e)}")
            
            # Check for authentication errors
            if "authentication" in str(e).lower() or "unauthorized" in str(e).lower():
                raise ProviderAuthenticationError(
                    f"OpenRouter authentication failed: {str(e)}",
                    provider_name="openrouter",
                ) from e

            # Check for content errors
            if "messages" in str(e).lower() and "content" in str(e).lower():
                self.logger.error(f"DEBUG: Content format error detected. Full error: {str(e)}")

            # Generic error
            raise ModelError(
                message=f"OpenRouter error: {str(e)}",
                details={"provider": "openrouter", "model": self.model_name},
            ) from e

    async def close(self) -> None:
        """
        Clean up resources (close the OpenAI client).
        """
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
        but the actual request is made using the OpenAI SDK.

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
        but the actual content extraction is done by the OpenAI SDK.

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