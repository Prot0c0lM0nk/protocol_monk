#!/usr/bin/env python3
"""
Model Client for Protocol Monk
==============================

Async HTTP client for Ollama LLM provider.
Supports streaming responses with proper error handling and timeout management.
"""

import aiohttp
import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from config.static import settings
from agent.model.exceptions import (
    ModelError,
    ModelTimeoutError,
    ModelConfigurationError,
    EmptyResponseError,
)


class ModelClient:
    """
    Async HTTP client for Ollama LLM provider.

    Responsibilities:
    - Handle async HTTP requests with proper streaming
    - Parse and yield response chunks
    - Convert provider errors to structured exceptions
    - Manage timeouts and connection pooling
    """

    def __init__(self, model_name: str):
        """
        Initialize the model client for Ollama.

        Args:
            model_name: LLM model identifier (e.g., "qwen3:4b")
        """
        self.model_name = model_name
        self.current_provider = "ollama"  # Set the provider name
        self.logger = logging.getLogger(__name__)

        # Use Ollama configuration from existing config.py
        # Use Ollama configuration from existing config.py
        self.ollama_url = settings.api.ollama_url
        self.timeout = settings.model.request_timeout

        # Get model options from existing config
        self.model_options = settings.model_options.chat_options

        # Session will be created on first use
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def set_model(self, model_name: str):
        """Switch to a different model and update context window in options."""
        self.model_name = model_name
        # Update model options with new model's context window if available
        from agent.model_manager import RuntimeModelManager

        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if model_info:
            new_context_window = model_info.context_window
            # Update both tool and chat options
            if "num_ctx" in self.model_options:
                self.model_options["num_ctx"] = new_context_window

    async def get_response_async(
        self, conversation_context: list, stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields response chunks from Ollama.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to stream response

        Yields:
            str: Response chunks as they arrive

        Raises:
            ModelTimeoutError: If request times out
            ModelError: If API returns error status
            EmptyResponseError: If response is empty
        """
        session = await self._get_session()

        # Prepare request payload for Ollama
        payload = self._prepare_payload(conversation_context, stream)

        headers = {"Content-Type": "application/json"}

        try:
            async with session.post(
                self.ollama_url, json=payload, headers=headers
            ) as response:
                # Check for HTTP errors
                if response.status >= 500:
                    error_text = await response.text()
                    raise ModelError(
                        message=f"Ollama client error: {response.status} - {error_text}",
                        details={
                            "provider": "ollama",
                            "model": self.model_name,
                            "status_code": response.status,
                        },
                    )
                elif response.status >= 400:
                    error_text = await response.text()
                    raise ModelError(
                        message=f"Ollama client error: {response.status} - {error_text}",
                        details={
                            "provider": "ollama",
                            "model": self.model_name,
                            "status_code": response.status,
                        },
                    )

                # Continue with response processing

                # Stream response
                if stream:
                    # Reset chunk counter for new request
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self._chunk_count = 0

                    # Ollama streams JSON objects separated by newlines
                    buffer = ""
                    async for line in response.content:
                        if line:
                            line_str = line.decode("utf-8")
                            buffer += line_str

                            # Process complete JSON objects
                            while "\n" in buffer:
                                line_json, buffer = buffer.split("\n", 1)
                                line_json = line_json.strip()
                                if not line_json:
                                    continue
                                # Collect full response for single debug log at the end
                                if self.logger.isEnabledFor(logging.DEBUG):
                                    chunk_count = getattr(self, "_chunk_count", 0) + 1
                                    self._chunk_count = chunk_count
                                    # Store chunks for final logging
                                    if not hasattr(self, "_response_chunks"):
                                        self._response_chunks = []
                                    try:
                                        chunk_data = json.loads(line_json)
                                        chunk_content = self._extract_chunk_content(
                                            chunk_data
                                        )
                                        if chunk_content:
                                            self._response_chunks.append(chunk_content)
                                    except json.JSONDecodeError:
                                        pass  # Ignore invalid chunks for logging

                                try:
                                    chunk_data = json.loads(line_json)
                                    chunk = self._extract_chunk_content(chunk_data)
                                    if chunk:
                                        yield chunk
                                except json.JSONDecodeError as e:
                                    self.logger.warning(
                                        f"Invalid JSON chunk: {line_json} - {e}"
                                    )
                                    continue

                    # Log the complete response at the end
                    if self.logger.isEnabledFor(logging.DEBUG) and hasattr(
                        self, "_response_chunks"
                    ):
                        full_response = "".join(self._response_chunks)
                        self.logger.debug(
                            f"Received complete response ({self._chunk_count} chunks): {full_response}"
                        )
                        # Clean up
                        delattr(self, "_response_chunks")
                        delattr(self, "_chunk_count")
                else:
                    # Non-streaming response
                    data = await response.json()
                    content = self._extract_full_content(data)
                    if content:
                        yield content
                    else:
                        raise EmptyResponseError(
                            message="Model returned an empty response",
                            details={"provider": "ollama", "model": self.model_name},
                        )
        except asyncio.TimeoutError:
            raise ModelTimeoutError(
                message="Model request timed out",
                timeout_seconds=self.timeout,
                details={"provider": "ollama", "model": self.model_name},
            )
        except aiohttp.ClientError as e:
            raise ModelError(
                message=f"Connection error: {str(e)}",
                details={"provider": "ollama", "model": self.model_name},
            )

    def _prepare_payload(
        self, conversation_context: list, stream: bool
    ) -> Dict[str, Any]:
        """Prepare request payload for Ollama."""
        # Use model options from existing config
        options = self.model_options.copy()

        return {
            "model": self.model_name,
            "messages": conversation_context,
            "stream": stream,
            "options": options,
        }

    def _extract_chunk_content(self, chunk_data: Dict[str, Any]) -> Optional[str]:
        """Extract content from streaming chunk."""
        try:
            # Ollama streaming format
            return chunk_data.get("message", {}).get("content", "")
        except (KeyError, TypeError) as e:
            self.logger.warning(f"Error extracting chunk content: {e}")
        return None

    def _extract_full_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """Extract content from non-streaming response."""
        try:
            # Ollama non-streaming format
            return response_data.get("message", {}).get("content", "")
        except (KeyError, TypeError) as e:
            self.logger.error(f"Error extracting full content: {e}")
        return None

    # Backward compatibility: synchronous wrapper
    def get_response(self, conversation_context: list, stream: bool = True):
        """
        Synchronous generator for backward compatibility.

        WARNING: This blocks the event loop! Use get_response_async() instead.
        """
        import warnings

        warnings.warn(
            "get_response() is deprecated. Use get_response_async() instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Run async generator in sync context (blocks event loop!)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async_gen = self.get_response_async(conversation_context, stream)
            while True:
                try:
                    yield loop.run_until_complete(async_gen.__anext__())
                except StopAsyncIteration:
                    break
        finally:
            loop.close()
