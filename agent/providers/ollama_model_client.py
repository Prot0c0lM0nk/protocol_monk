#!/usr/bin/env python3
"""
Ollama Model Client Provider
============================

Ollama-specific implementation of BaseModelClient.
Preserves all existing Ollama-specific logic while implementing the provider interface.
"""

import warnings

import aiohttp
import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from agent.base_model_client import BaseModelClient
from agent.model_manager import RuntimeModelManager
from config.static import settings
from exceptions import (
    EmptyResponseError,
    ModelError,
    ModelTimeoutError,
)


class OllamaModelClient(BaseModelClient):
    """
    Ollama-specific implementation with streaming support, error handling, and tool calling.

    This class contains all the existing Ollama functionality from the original
    ModelClient, but implements the BaseModelClient interface for consistency
    across providers.
    """

    def __init__(self, model_name: str, provider_config: Optional[Dict] = None):
        """
        Initialize the Ollama model client.

        Args:
            model_name: LLM model identifier (e.g., "qwen3:4b")
            provider_config: Provider-specific configuration (uses settings if None)
        """
        # Initialize base class with default config
        if provider_config is None:
            # Use Ollama-specific defaults from settings
            provider_config = {
                "timeout": settings.model.request_timeout,
                "max_retries": 3,
                "retry_delay": 1.0,
            }

        super().__init__(model_name, provider_config)

        # Ollama-specific configuration
        self.ollama_url = settings.api.ollama_url

        # Load the default options first
        self.model_options = (
            settings.model_options.chat_options.copy()
        )  # Good practice to copy mutable dicts

        # Run the full setup logic immediately
        # This looks up the model in your ollama_map.json and applies
        # the specific context window (e.g., 40k) right now.
        self._setup_model(model_name)

        self._session: Optional[aiohttp.ClientSession] = None

    def _setup_model(self, model_name: str) -> None:
        """
        Set up model-specific configuration.

        Args:
            model_name: Name of the model to set up
        """
        self.model_name = model_name

        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if model_info:
            new_context_window = model_info.context_window
            if "num_ctx" in self.model_options:
                self.model_options["num_ctx"] = new_context_window

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session.

        Returns:
            aiohttp.ClientSession: HTTP session for API requests
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def get_response_async(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Union[str, Dict], None]:
        """
        Async generator that yields response chunks from Ollama.

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
        session = await self._get_session()
        payload = self._prepare_payload(conversation_context, stream, tools)
        headers = {"Content-Type": "application/json"}

        try:
            async with session.post(
                self.ollama_url, json=payload, headers=headers
            ) as response:

                await self._check_error_status(response)

                if stream:
                    # Direct streaming - Ollama provides complete JSON per line
                    # No buffering needed - each line is a complete response object
                    async for line in response.content:
                        if not line.strip():
                            continue

                        try:
                            line_str = line.decode("utf-8").strip()
                            if not line_str:
                                continue

                            # Handle potential cloud server errors
                            # Cloud models might return non-JSON content on errors
                            try:
                                chunk_data = json.loads(line_str)
                            except json.JSONDecodeError as e:
                                # Check if this is an HTML error page or non-JSON response
                                if (
                                    line_str.startswith("<")
                                    or "html" in line_str.lower()
                                ):
                                    self.logger.error(
                                        "Cloud server returned HTML error page: %s",
                                        line_str[:100],
                                    )
                                    raise ModelError(
                                        message="Cloud model server returned HTML error page",
                                        details={
                                            "provider": "ollama",
                                            "model": self.model_name,
                                            "response_snippet": line_str[:200],
                                        },
                                    )
                                elif (
                                    "error" in line_str.lower()
                                    or "status" in line_str.lower()
                                ):
                                    # Might be a plain text error message
                                    self.logger.error(
                                        "Cloud server returned error text: %s", line_str
                                    )
                                    raise ModelError(
                                        message=f"Cloud model error: {line_str}",
                                        details={
                                            "provider": "ollama",
                                            "model": self.model_name,
                                            "raw_response": line_str,
                                        },
                                    )
                                else:
                                    # Genuine JSON decoding issue
                                    self.logger.warning(
                                        "Invalid JSON chunk from Ollama: %s - %s",
                                        line_str,
                                        e,
                                    )
                                    continue

                            # Ollama sends complete JSON objects per line
                            if "message" in chunk_data:
                                message = chunk_data["message"]

                                # Check for text content first
                                if "content" in message and message["content"]:
                                    yield message["content"]

                                # Check for complete tool calls (Ollama format - direct JSON)
                                elif "tool_calls" in message and message["tool_calls"]:
                                    yield chunk_data  # Return complete response with tool calls
                                # Log debug info if enabled
                                if "content" in message and message["content"]:
                                    self.logger.debug(
                                        "Ollama chunk: %s", message["content"]
                                    )
                                elif "tool_calls" in message and message["tool_calls"]:
                                    self.logger.debug(
                                        "Ollama tool calls: %s", message["tool_calls"]
                                    )
                        except Exception as e:
                            self.logger.error(
                                "Error processing Ollama stream chunk: %s", e
                            )
                            continue
                else:
                    data = await response.json()
                    content = self._extract_full_content(data)
                    if content:
                        yield content
                    else:
                        raise EmptyResponseError(
                            message="Model returned an empty response",
                            details={"provider": "ollama", "model": self.model_name},
                        )

        except asyncio.TimeoutError as exc:
            raise ModelTimeoutError(
                message="Model request timed out",
                timeout_seconds=self.timeout,
                details={"provider": "ollama", "model": self.model_name},
            ) from exc
        except (aiohttp.ClientError, json.JSONDecodeError) as e:
            raise ModelError(
                message=f"Server communication error: {str(e)}",
                details={"provider": "ollama", "model": self.model_name},
            ) from e
        except Exception as e:
            # Safety net for any other unexpected errors
            self.logger.exception("Unexpected error communicating with Ollama server")
            raise ModelError(
                message=f"Unexpected server error: {str(e)}",
                details={"provider": "ollama", "model": self.model_name},
            ) from e

    async def _check_error_status(self, response: aiohttp.ClientResponse):
        """
        Check for HTTP errors and raise appropriate exceptions.

        Args:
            response: HTTP response to check for errors

        Raises:
            ModelError: If HTTP error status is detected
        """
        if response.status >= 400:
            error_text = await response.text()

            # Enhanced error handling for cloud models
            if response.status >= 500:
                # Cloud server internal error - might be temporary
                self.logger.warning(
                    "Cloud model server returned %s error for %s: %s",
                    response.status,
                    self.model_name,
                    error_text[:200],
                )

                # Provide more specific error messages for cloud issues
                if response.status == 500:
                    raise ModelError(
                        message=f"Cloud model server internal error (500). This may be temporary. Try again or switch models.",
                        details={
                            "provider": "ollama",
                            "model": self.model_name,
                            "status_code": response.status,
                            "error_details": error_text[:300],
                            "suggestion": "Try clearing context or switching to a different model",
                        },
                    )
                elif response.status == 502:
                    raise ModelError(
                        message="Cloud model gateway error (502). The model server is unavailable.",
                        details={
                            "provider": "ollama",
                            "model": self.model_name,
                            "status_code": response.status,
                            "suggestion": "Try again later or use a local model",
                        },
                    )
                elif response.status == 503:
                    raise ModelError(
                        message="Cloud model service unavailable (503). The model is temporarily overloaded.",
                        details={
                            "provider": "ollama",
                            "model": self.model_name,
                            "status_code": response.status,
                            "suggestion": "Try clearing context or waiting a moment",
                        },
                    )

            # Standard error handling for 4xx errors
            raise ModelError(
                message=f"Ollama client error: {response.status} - {error_text}",
                details={
                    "provider": "ollama",
                    "model": self.model_name,
                    "status_code": response.status,
                },
            )

    def _prepare_payload(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Args:
            conversation_context: List of conversation messages
            stream: Whether to enable streaming

        Returns:
            Dict[str, Any]: Request payload for Ollama API
        """
        options = self.model_options.copy()
        payload = {
            "model": self.model_name,
            "messages": conversation_context,
            "stream": stream,
            "options": options,
        }
        if tools:
            payload["tools"] = tools  # Ollama accepts OpenAI format
        return payload

    def _extract_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract content from response data.

        Args:
            response_data: Response data dictionary

        Returns:
            Optional[str]: Extracted content or None if error
        """
        try:
            return response_data.get("message", {}).get("content", "")
        except (KeyError, TypeError) as e:
            self.logger.warning("Error extracting content: %s", e)
        return None

    def _extract_chunk_content(self, chunk_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract content from streaming chunk.

        Args:
            chunk_data: Streaming chunk data dictionary

        Returns:
            Optional[str]: Extracted content or None if error
        """
        try:
            return chunk_data.get("message", {}).get("content", "")
        except (KeyError, TypeError) as e:
            self.logger.warning("Error extracting chunk content: %s", e)
        return None

    def _extract_full_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract content from non-streaming response.

        Args:
            response_data: Complete response data dictionary

        Returns:
            Optional[str]: Extracted content or None if error
        """
        try:
            return response_data.get("message", {}).get("content", "")
        except (KeyError, TypeError) as e:
            self.logger.error("Error extracting full content: %s", e)
        return None

    def supports_tools(self) -> bool:
        """
        Return True if provider supports tool/function calling.

        Returns:
            bool: Ollama supports JSON tool calling
        """
        return True

    async def close(self) -> None:
        """
        Close the HTTP session.
        """
        if self._session and not self._session.closed:
            await self._session.close()

    def get_response(
        self, conversation_context: List[Dict[str, str]], stream: bool = True
    ):
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
