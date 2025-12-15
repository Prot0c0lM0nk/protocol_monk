#!/usr/bin/env python3
"""
OpenRouter Model Client Provider
================================

OpenRouter-specific implementation of BaseModelClient.
Provides access to multiple LLM models through the OpenRouter API.
"""

import warnings

import aiohttp
import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from agent.base_model_client import BaseModelClient
from agent.buffered_model_client import create_buffered_response
from config.static import settings
from exceptions import (
    EmptyResponseError,
    ModelError,
    ModelTimeoutError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
)


class OpenRouterModelClient(BaseModelClient):
    """
    OpenRouter-specific implementation with streaming support and error handling.
    
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
        
        # OpenRouter-specific configuration
        self.base_url = "https://openrouter.ai/api/v1"
        self.chat_url = f"{self.base_url}/chat/completions"
        
        # Validate API key during initialization
        try:
            self.api_key = self._get_api_key()
        except ProviderConfigurationError as e:
            # Re-raise with more context
            raise ProviderConfigurationError(
                f"Cannot initialize OpenRouter client: {e.message}",
                provider_name="openrouter",
                details=e.details
            ) from e
        
        # Model options (OpenRouter uses OpenAI-compatible format)
        self.model_options = {
            "temperature": 0.7,
            "max_tokens": 4096,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }
        
        self._session: Optional[aiohttp.ClientSession] = None
        
        # State variables for debug logging
        self._chunk_count = 0
        self._response_chunks: List[str] = []
    
    def _get_api_key(self) -> str:
        """
        Get OpenRouter API key from environment variables.
        
        Returns:
            str: API key
            
        Raises:
            ProviderConfigurationError: If API key is not configured
        """
        api_key = getattr(settings.environment, 'openrouter_api_key', None) or \
                  settings.environment.openrouter_api_key if hasattr(settings.environment, 'openrouter_api_key') else None
        
        if not api_key:
            # Try environment variable directly
            import os
            api_key = os.getenv("OPENROUTER_API_KEY")
        
        if not api_key:
            raise ProviderConfigurationError(
                "OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable.",
                provider_name="openrouter"
            )
        
        return api_key
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session with OpenRouter headers.
        
        Returns:
            aiohttp.ClientSession: HTTP session for API requests
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/protocol-monk",  # Optional: your app URL
                "X-Title": "Protocol Monk",  # Optional: your app name
            }
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self._session
    
    async def get_response_async(
        self, conversation_context: List[Dict[str, str]], stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields response chunks from OpenRouter.
        
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
        
        try:
            async with session.post(self.chat_url, json=payload) as response:
                await self._check_error_status(response)
                
                if stream:
                    # Use buffered response to handle split tool calls
                    raw_generator = self._process_stream_response(response)
                    buffered_generator = create_buffered_response(raw_generator)
                    async for chunk in buffered_generator:
                        yield chunk
                else:
                    data = await response.json()
                    content = self._extract_full_content(data)
                    if content:
                        yield content
                    else:
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
        except (aiohttp.ClientError, json.JSONDecodeError) as e:
            raise ModelError(
                message=f"Server communication error: {str(e)}",
                details={"provider": "openrouter", "model": self.model_name},
            ) from e
        except Exception as e:
            # Safety net for any other unexpected errors
            self.logger.exception("Unexpected error communicating with OpenRouter server")
            raise ModelError(
                message=f"Unexpected server error: {str(e)}",
                details={"provider": "openrouter", "model": self.model_name},
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
            
            if response.status == 401:
                raise ProviderAuthenticationError(
                    f"OpenRouter authentication failed: {error_text}",
                    provider_name="openrouter"
                )
            elif response.status == 429:
                # Rate limit error
                retry_after = response.headers.get("Retry-After")
                raise ModelError(
                    f"OpenRouter rate limit exceeded: {error_text}",
                    details={
                        "provider": "openrouter",
                        "model": self.model_name,
                        "status_code": response.status,
                        "retry_after": retry_after,
                    },
                )
            else:
                raise ModelError(
                    f"OpenRouter client error: {response.status} - {error_text}",
                    details={
                        "provider": "openrouter",
                        "model": self.model_name,
                        "status_code": response.status,
                    },
                )
    
    async def _process_stream_response(
        self, response: aiohttp.ClientResponse
    ) -> AsyncGenerator[str, None]:
        """
        Process streaming response from OpenRouter (Server-Sent Events format).
        
        Args:
            response: aiohttp.ClientResponse from the API call
            
        Yields:
            str: Content chunks from the response
        """
        self._initialize_stream_state()
        
        async for line in response.content:
            if not line:
                continue
            
            line_str = line.decode("utf-8").strip()
            
            # Server-Sent Events format: "data: {json}"
            if line_str.startswith("data: "):
                json_str = line_str[6:]  # Remove "data: " prefix
                
                if json_str == "[DONE]":
                    break
                
                try:
                    chunk_data = json.loads(json_str)
                    chunk_content = self._extract_chunk_content(chunk_data)
                    
                    if chunk_content:
                        self._log_debug_info(chunk_content)
                        yield chunk_content
                        
                except json.JSONDecodeError as e:
                    self.logger.warning("Invalid JSON chunk: %s - %s", json_str, e)
                    continue
        
        self._log_complete_response()
    
    def _initialize_stream_state(self) -> None:
        """
        Initialize debug logging state for stream processing.
        """
        if self.logger.isEnabledFor(logging.DEBUG):
            self._chunk_count = 0
            self._response_chunks = []
    
    def _log_debug_info(self, chunk_content: str) -> None:
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
    
    def _prepare_payload(self, conversation_context: List[Dict[str, str]], stream: bool) -> Dict[str, Any]:
        """
        Prepare request payload for OpenRouter (OpenAI-compatible format).
        
        Args:
            conversation_context: List of conversation messages
            stream: Whether to enable streaming
            
        Returns:
            Dict[str, Any]: Request payload for OpenRouter API
        """
        return {
            "model": self.model_name,
            "messages": conversation_context,
            "stream": stream,
            **self.model_options
        }
    
    def _extract_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract content from response data.
        
        Args:
            response_data: Response data dictionary
            
        Returns:
            Optional[str]: Extracted content or None if error
        """
        try:
            # OpenRouter uses OpenAI format
            if "choices" in response_data and response_data["choices"]:
                return response_data["choices"][0]["message"]["content"]
            return None
        except (KeyError, TypeError, IndexError) as e:
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
            # OpenRouter streaming format
            if "choices" in chunk_data and chunk_data["choices"]:
                delta = chunk_data["choices"][0].get("delta", {})
                return delta.get("content", "")
            return None
        except (KeyError, TypeError, IndexError) as e:
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
        return self._extract_content(response_data)
    
    def supports_tools(self) -> bool:
        """
        Return True if provider supports tool/function calling.
        
        Returns:
            bool: OpenRouter supports tools for most models
        """
        return True
    
    async def close(self) -> None:
        """
        Close the HTTP session.
        """
        if self._session and not self._session.closed:
            await self._session.close()
    
    def get_response(self, conversation_context: List[Dict[str, str]], stream: bool = True):
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
