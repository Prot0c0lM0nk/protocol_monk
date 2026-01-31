#!/usr/bin/env python3
"""
MLX LM Model Client
====================

Provider implementation for MLX LM models.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from mlx_lm import load, generate, stream_generate
from mlx_lm.tokenizer_utils import TokenizerWrapper
from mlx_lm import sample_utils

from agent.base_model_client import BaseModelClient
from exceptions import EmptyResponseError, ModelError, ModelTimeoutError


class MLXLMModelClient(BaseModelClient):
    """
    Provider implementation for MLX LM models.

    This class implements the BaseModelClient interface for MLX LM models,
    enabling seamless integration with the agent's multi-provider architecture.
    """

    def __init__(
        self, model_name: str, provider_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the MLX LM model client.

        Args:
            model_name: The model identifier (e.g., "mlx-community/Llama-3.2-3B-Instruct-4bit")
            provider_config: Provider-specific configuration
        """
        super().__init__(model_name, provider_config)
        self.model = None
        self.tokenizer = None
        self._loaded = False

        # MLX LM specific configuration - use settings if available, else defaults
        from config.static import settings
        mlx_config = settings.api.providers.get("mlx_lm", {})

        self.system_prompt = provider_config.get("system_prompt", None) if provider_config else None
        self.max_tokens = provider_config.get("max_tokens", mlx_config.get("max_tokens", 512)) if provider_config else mlx_config.get("max_tokens", 512)
        self.temperature = provider_config.get("temperature", mlx_config.get("temperature", 0.1)) if provider_config else mlx_config.get("temperature", 0.1)
        self.top_p = provider_config.get("top_p", mlx_config.get("top_p", 0.9)) if provider_config else mlx_config.get("top_p", 0.9)
    async def load_model(self) -> None:
        """
        Load the MLX LM model and tokenizer.
        """
        if self._loaded:
            return

        try:
            # Load the model and tokenizer
            self.model, self.tokenizer = load(self.model_name)
            self._loaded = True
            self.logger.info(f"Loaded MLX LM model: {self.model_name}")
        except Exception as e:
            raise ModelError(
                f"Failed to load MLX LM model '{self.model_name}': {e}"
            ) from e

    async def get_response_async(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Union[str, Dict], None]:
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
        # Ensure model is loaded
        if not self._loaded:
            await self.load_model()

        try:
            # Prepare the prompt using the chat template
            messages = conversation_context
            if self.system_prompt:
                messages = [{"role": "system", "content": self.system_prompt}] + messages

            prompt = self.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True
            )

            if stream:
                # Stream the response
                async for response in self._stream_generate(prompt):
                    yield response
            else:
                # Generate the full response
                response = await self._generate(prompt)
                if response:
                    yield response
                else:
                    raise EmptyResponseError(
                        "Model returned an empty response",
                        details={"model_name": self.model_name},
                    )

        except asyncio.TimeoutError as e:
            raise ModelTimeoutError(
                f"Request to MLX LM model '{self.model_name}' timed out",
                details={"model_name": self.model_name},
            ) from e
        except Exception as e:
            raise ModelError(
                f"Error generating response from MLX LM model '{self.model_name}': {e}",
                details={"model_name": self.model_name},
            ) from e

    async def _stream_generate(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Stream the response from the model.

        Args:
            prompt: The prompt to generate from

        Yields:
            str: Response chunks
        """
        loop = asyncio.get_event_loop()

        def _generate():
            """Generate the response in a synchronous context."""
            # Tokenize the prompt if not already tokenized
            tokenized_prompt = prompt
            if isinstance(tokenized_prompt, str):
                if self.tokenizer.chat_template is not None:
                    messages = [{"role": "user", "content": tokenized_prompt}]
                    tokenized_prompt = self.tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True
                    )
                else:
                    tokenized_prompt = self.tokenizer.encode(tokenized_prompt)

            # Create sampler for temperature/top_p
            sampler = sample_utils.make_sampler(
                temp=self.temperature,
                top_p=self.top_p,
            )

            for response in stream_generate(
                self.model,
                self.tokenizer,
                prompt=tokenized_prompt,
                max_tokens=self.max_tokens,
                sampler=sampler,
            ):
                yield response.text
                yield response.text

        # Run the synchronous generator in a thread
        async def _async_generate():
            """Wrap the synchronous generator in an async context."""
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(None, lambda: list(_generate()))
            for chunk in await future:
                yield chunk

        async for chunk in _async_generate():
            yield chunk

    async def _generate(self, prompt: str) -> Optional[str]:
        """
        Generate a full response from the model.

        Args:
            prompt: The prompt to generate from

        Returns:
            Optional[str]: The generated response or None if empty
        """
        loop = asyncio.get_event_loop()

        def _generate():
            """Generate the response in a synchronous context."""
            # Tokenize the prompt if not already tokenized
            tokenized_prompt = prompt
            if isinstance(tokenized_prompt, str):
                if self.tokenizer.chat_template is not None:
                    messages = [{"role": "user", "content": tokenized_prompt}]
                    tokenized_prompt = self.tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True
                    )
                else:
                    tokenized_prompt = self.tokenizer.encode(tokenized_prompt)

            # Create sampler for temperature/top_p
            sampler = sample_utils.make_sampler(
                temp=self.temperature,
                top_p=self.top_p,
            )

            return generate(
                self.model,
                self.tokenizer,
                prompt=tokenized_prompt,
                max_tokens=self.max_tokens,
                sampler=sampler,
            )

        # Run the synchronous function in a thread
        future = loop.run_in_executor(None, _generate)
        response = await future

        return response if response else None

    def _prepare_payload(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Convert generic conversation format to provider-specific request payload.

        Args:
            conversation_context: List of conversation messages
            stream: Whether to enable streaming

        Returns:
            Dict[str, Any]: Provider-specific request payload
        """
        # MLX LM uses the chat template directly, so no additional payload preparation is needed
        return {
            "messages": conversation_context,
            "stream": stream,
        }

    def _extract_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract text content from provider-specific response format.

        Args:
            response_data: Provider-specific response data

        Returns:
            Optional[str]: Extracted content or None if invalid
        """
        # MLX LM responses are already in text format
        return response_data.get("text")

    async def close(self) -> None:
        """
        Clean up resources (HTTP sessions, connections, etc.).
        """
        # MLX LM models are loaded in memory, so no cleanup is needed
        self._loaded = False
        self.model = None
        self.tokenizer = None

    def supports_tools(self) -> bool:
        """
        Return True if provider supports tool/function calling.

        Returns:
            bool: Whether provider supports tools
        """
        return False
