#!/usr/bin/env python3
"""
Ollama Model Client Provider (Official SDK Version)
===================================================

Ollama-specific implementation using the official Ollama SDK.
Note: The official ollama Python SDK is synchronous, so we wrap it in asyncio.
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

# Note: Official ollama SDK is synchronous
# We'll wrap it in asyncio for compatibility
import ollama

from agent.base_model_client import BaseModelClient
from agent.model_manager import RuntimeModelManager
from config.static import settings
from exceptions import (
    EmptyResponseError,
    ModelError,
    ModelTimeoutError,
)


class OllamaModelClientSDK(BaseModelClient):
    """
    Ollama-specific implementation using the official Ollama SDK.

    The official ollama SDK is synchronous, so we wrap it in asyncio.run_in_executor
    to maintain compatibility with our async architecture.
    """

    def __init__(self, model_name: str, provider_config: Optional[Dict] = None):
        """
        Initialize the Ollama model client.

        Args:
            model_name: LLM model identifier (e.g., "qwen3:4b")
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

        # Ollama-specific configuration
        self.ollama_url = self._normalize_ollama_host(settings.api.ollama_url)

        # Load the default options
        self.model_options = settings.model_options.chat_options.copy()

        # Set up model-specific configuration
        self._setup_model(model_name)

        # Initialize the Ollama client
        self.client = ollama.Client(host=self.ollama_url)

    @staticmethod
    def _normalize_ollama_host(host: str) -> str:
        """Normalize configured Ollama URL to a base host for the official SDK."""
        normalized = (host or "").strip().rstrip("/")
        if normalized.endswith("/api/chat"):
            normalized = normalized[: -len("/api/chat")]
        elif normalized.endswith("/api/generate"):
            normalized = normalized[: -len("/api/generate")]
        elif normalized.endswith("/api"):
            normalized = normalized[: -len("/api")]
        return normalized or "http://localhost:11434"

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

    async def get_response_async(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Union[str, Dict], None]:
        """
        Get response from Ollama using the official SDK.

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
            loop = asyncio.get_event_loop()

            def _next_chunk(iterator):
                try:
                    return next(iterator), False
                except StopIteration:
                    return None, True

            # Prepare messages (Ollama SDK requires tool_call.function.arguments as dict)
            messages = self._normalize_messages_for_ollama(conversation_context)

            # Build request parameters
            request_params = {
                "model": self.model_name,
                "messages": messages,
                "stream": stream,
                "options": self.model_options,
            }

            # Add tools if provided (Ollama format)
            if tools:
                request_params["tools"] = tools

            self.logger.info(
                "Making Ollama request to model: %s (stream=%s)",
                self.model_name,
                stream,
            )

            if stream:
                # Streaming response: run blocking iterator advancement in executor.
                stream_response = await loop.run_in_executor(
                    None, lambda: iter(self.client.chat(**request_params))
                )

                while True:
                    chunk, done = await loop.run_in_executor(
                        None, _next_chunk, stream_response
                    )
                    if done:
                        break

                    # Extract message
                    message = chunk.get("message", {})

                    # Check for thinking content
                    if "thinking" in message and message["thinking"]:
                        yield {"type": "thinking", "content": message["thinking"]}

                    # Check for text content
                    if "content" in message and message["content"]:
                        self.logger.debug(
                            f"Yielding content chunk: {message['content'][:100]}"
                        )
                        yield message["content"]

                    # Check for tool calls (Ollama format)
                    if "tool_calls" in message and message["tool_calls"]:
                        self.logger.info(f"Yielding tool call chunk: {chunk}")
                        yield chunk  # Return complete response with tool calls
            else:
                # Non-streaming response
                response = await loop.run_in_executor(
                    None, lambda: self.client.chat(**request_params)
                )

                # Extract content
                message = response.get("message", {})
                content = message.get("content")

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
        except Exception as e:
            error_text = str(e).lower()

            if "404 page not found" in error_text:
                raise ModelError(
                    message=(
                        f"Ollama endpoint not found at {self.ollama_url}. "
                        "Configure PROTOCOL_OLLAMA_URL as a base host "
                        "(for example: http://localhost:11434)."
                    ),
                    details={"provider": "ollama", "model": self.model_name},
                ) from e

            # Check for connection errors
            if "connection" in error_text or "refused" in error_text:
                raise ModelError(
                    message=f"Cannot connect to Ollama server at {self.ollama_url}",
                    details={"provider": "ollama", "model": self.model_name},
                ) from e

            # Generic error
            raise ModelError(
                message=f"Ollama error: {str(e)}",
                details={"provider": "ollama", "model": self.model_name},
            ) from e

    @staticmethod
    def _normalize_messages_for_ollama(
        conversation_context: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Normalize historical messages for Ollama SDK strict validation.

        Ollama's pydantic model requires:
          tool_calls[].function.arguments -> dict
        while other providers may store this field as a JSON string.
        """
        normalized: List[Dict[str, Any]] = []
        for raw_msg in conversation_context or []:
            if not isinstance(raw_msg, dict):
                continue

            msg = dict(raw_msg)
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                coerced_calls: List[Dict[str, Any]] = []
                for raw_call in tool_calls:
                    if not isinstance(raw_call, dict):
                        continue
                    call = dict(raw_call)
                    function = call.get("function")
                    if isinstance(function, dict):
                        fn = dict(function)
                        args = fn.get("arguments")
                        if isinstance(args, str):
                            try:
                                parsed = json.loads(args)
                                fn["arguments"] = parsed if isinstance(parsed, dict) else {}
                            except json.JSONDecodeError:
                                fn["arguments"] = {}
                        elif args is None:
                            fn["arguments"] = {}
                        elif not isinstance(args, dict):
                            fn["arguments"] = {}
                        call["function"] = fn
                    coerced_calls.append(call)
                msg["tool_calls"] = coerced_calls

            normalized.append(msg)
        return normalized

    async def close(self) -> None:
        """
        Clean up resources.

        Note: The Ollama SDK doesn't require explicit cleanup,
        but we keep this method for compatibility with BaseModelClient.
        """
        pass

    def _prepare_payload(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare request payload for Ollama.

        Note: This method is kept for compatibility with BaseModelClient,
        but the actual request is made using the Ollama SDK.

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
            "options": self.model_options,
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _extract_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract content from response data.

        Note: This method is kept for compatibility with BaseModelClient,
        but the actual content extraction is done by the Ollama SDK.

        Args:
            response_data: Response data dictionary

        Returns:
            Optional[str]: Extracted content or None if error
        """
        if "message" in response_data:
            return response_data["message"].get("content")
        return None

    def supports_tools(self) -> bool:
        """
        Return True if provider supports tool/function calling.

        Returns:
            bool: Ollama supports tools via its API
        """
        return True
