#!/usr/bin/env python3
"""
Model Client for Protocol Monk
==============================

Async HTTP client for Ollama LLM provider.
Supports streaming responses with proper error handling and timeout management.
"""

import warnings

import aiohttp
import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from agent.model.exceptions import (
    EmptyResponseError,
    ModelError,
    ModelTimeoutError,
)
from agent.model_manager import RuntimeModelManager
from config.static import settings


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
        self.current_provider = "ollama"
        self.logger = logging.getLogger(__name__)

        self.ollama_url = settings.api.ollama_url
        self.timeout = settings.model.request_timeout
        self.model_options = settings.model_options.chat_options

        self._session: Optional[aiohttp.ClientSession] = None

        # State variables for debug logging
        self._chunk_count = 0
        self._response_chunks: List[str] = []

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

        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if model_info:
            new_context_window = model_info.context_window
            if "num_ctx" in self.model_options:
                self.model_options["num_ctx"] = new_context_window

    async def _check_error_status(self, response: aiohttp.ClientResponse):
        """Check for HTTP errors and raise appropriate exceptions."""
        if response.status >= 400:
            error_text = await response.text()
            raise ModelError(
                message=f"Ollama client error: {response.status} - {error_text}",
                details={
                    "provider": "ollama",
                    "model": self.model_name,
                    "status_code": response.status,
                },
            )

    async def _process_stream_response(
        self, response: aiohttp.ClientResponse
    ) -> AsyncGenerator[str, None]:
        """Process streaming response from Ollama."""
        # Reset state
        if self.logger.isEnabledFor(logging.DEBUG):
            self._chunk_count = 0
            self._response_chunks = []

        buffer = ""
        async for line in response.content:
            if not line:
                continue

            line_str = line.decode("utf-8")
            buffer += line_str

            while "\n" in buffer:
                line_json, buffer = buffer.split("\n", 1)
                line_json = line_json.strip()
                if not line_json:
                    continue

                try:
                    chunk_data = json.loads(line_json)
                    chunk_content = self._extract_chunk_content(chunk_data)

                    # Accumulate for debug
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self._chunk_count += 1
                        if chunk_content:
                            self._response_chunks.append(chunk_content)

                    if chunk_content:
                        yield chunk_content

                except json.JSONDecodeError as e:
                    self.logger.warning("Invalid JSON chunk: %s - %s", line_json, e)
                    continue

        # Log complete response
        if self.logger.isEnabledFor(logging.DEBUG) and self._response_chunks:
            full_response = "".join(self._response_chunks)
            self.logger.debug(
                "Received complete response (%d chunks): %s",
                self._chunk_count,
                full_response,
            )

    async def get_response_async(
        self, conversation_context: list, stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields response chunks from Ollama.
        """
        session = await self._get_session()
        payload = self._prepare_payload(conversation_context, stream)
        headers = {"Content-Type": "application/json"}

        try:
            async with session.post(
                self.ollama_url, json=payload, headers=headers
            ) as response:

                await self._check_error_status(response)

                if stream:
                    async for chunk in self._process_stream_response(response):
                        yield chunk
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
        except aiohttp.ClientError as e:
            raise ModelError(
                message=f"Connection error: {str(e)}",
                details={"provider": "ollama", "model": self.model_name},
            ) from e

    def _prepare_payload(
        self, conversation_context: list, stream: bool
    ) -> Dict[str, Any]:
        """Prepare request payload for Ollama."""
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
            return chunk_data.get("message", {}).get("content", "")
        except (KeyError, TypeError) as e:
            self.logger.warning("Error extracting chunk content: %s", e)
        return None

    def _extract_full_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """Extract content from non-streaming response."""
        try:
            return response_data.get("message", {}).get("content", "")
        except (KeyError, TypeError) as e:
            self.logger.error("Error extracting full content: %s", e)
        return None

    def get_response(self, conversation_context: list, stream: bool = True):
        """
        Synchronous generator for backward compatibility.
        WARNING: This blocks the event loop! Use get_response_async() instead.
        """
        warnings.warn(
            "get_response() is deprecated. Use get_response_async() instead.",
            DeprecationWarning,
            stacklevel=2,
        )

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
