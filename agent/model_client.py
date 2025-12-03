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
        """
        Get or create aiohttp session.

        Returns:
            aiohttp.ClientSession: HTTP session for API requests
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """
        Close the HTTP session.
        """
        if self._session and not self._session.closed:
            await self._session.close()

    def set_model(self, model_name: str):
        """
        Switch to a different model and update context window in options.

        Args:
            model_name: Name of the model to switch to
        """
        self.model_name = model_name

        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if model_info:
            new_context_window = model_info.context_window
            if "num_ctx" in self.model_options:
                self.model_options["num_ctx"] = new_context_window

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
        """
        Process streaming response from Ollama.

        Args:
            response: aiohttp.ClientResponse from the API call

        Yields:
            str: Content chunks from the response
        """
        self._initialize_stream_state()

        buffer = ""
        async for line in response.content:
            if not line:
                continue

            line_str = line.decode("utf-8")
            buffer += line_str

            async for chunk_content in self._process_buffer(buffer):
                if chunk_content:
                    yield chunk_content
                buffer = self._update_buffer(buffer)

        self._log_complete_response()

    def _initialize_stream_state(self) -> None:
        """
        Initialize debug logging state for stream processing.
        """
        if self.logger.isEnabledFor(logging.DEBUG):
            self._chunk_count = 0
            self._response_chunks = []

    async def _process_buffer(self, buffer: str) -> AsyncGenerator[str, None]:
        """
        Process buffer content and yield valid chunks.

        Args:
            buffer: Current buffer content

        Yields:
            str: Valid content chunks
        """
        while "\n" in buffer:
            line_json, remaining_buffer = buffer.split("\n", 1)
            line_json = line_json.strip()
            buffer = remaining_buffer

            if not line_json:
                continue

            chunk_content = await self._process_json_line(line_json)
            if chunk_content:
                yield chunk_content

    async def _process_json_line(self, line_json: str) -> str | None:
        """
        Process a single JSON line and extract content.

        Args:
            line_json: JSON string to process

        Returns:
            str | None: Extracted content or None if invalid
        """
        try:
            chunk_data = json.loads(line_json)
            chunk_content = self._extract_chunk_content(chunk_data)

            self._log_debug_info(chunk_content)
            return chunk_content

        except json.JSONDecodeError as e:
            self.logger.warning("Invalid JSON chunk: %s - %s", line_json, e)
            return None

    def _update_buffer(self, buffer: str) -> str:
        """
        Update buffer after processing lines.

        Args:
            buffer: Current buffer state

        Returns:
            str: Updated buffer content
        """
        if "\n" in buffer:
            _, remaining = buffer.split("\n", 1)
            return remaining
        return buffer

    def _log_debug_info(self, chunk_content: str | None) -> None:
        """
        Log debug information for processed chunks.

        Args:
            chunk_content: Content chunk to log debug info for
        """
        if self.logger.isEnabledFor(logging.DEBUG) and chunk_content:
            self._chunk_count += 1
            self._response_chunks.append(chunk_content)

    def _log_complete_response(self) -> None:
        """
        Log the complete accumulated response.
        """
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
        """
        Prepare request payload for Ollama.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to enable streaming

        Returns:
            Dict[str, Any]: Request payload for Ollama API
        """
        options = self.model_options.copy()
        return {
            "model": self.model_name,
            "messages": conversation_context,
            "stream": stream,
            "options": options,
        }

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

    def get_response(self, conversation_context: list, stream: bool = True):
        """
        Synchronous generator for backward compatibility.
        WARNING: This blocks the event loop! Use get_response_async() instead.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to stream the response (default: True)

        Yields:
            str: Response content chunks
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
