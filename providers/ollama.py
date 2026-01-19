import time
import logging
from typing import AsyncIterator, List, Dict, Any, Optional

from ollama import AsyncClient

from protocol_monk.agent.structs import Message, ProviderSignal, ToolRequest
from protocol_monk.providers.base import BaseProvider
from protocol_monk.config.settings import Settings
from protocol_monk.exceptions.provider import ProviderError

logger = logging.getLogger("OllamaProvider")


class OllamaProvider(BaseProvider):
    """
    Adapter for Ollama (Local & Cloud).
    Maps native SDK objects -> ProviderSignal.
    """

    def __init__(self, settings: Settings):
        self.host = settings.ollama_host
        self.api_key = settings.ollama_api_key

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = AsyncClient(host=self.host, headers=headers)

    async def validate_connection(self) -> bool:
        try:
            await self.client.list()
            return True
        except Exception as e:
            logger.error(f"Ollama Connection Failed: {e}")
            return False

    async def stream_chat(
        self,
        messages: List[Message],
        model_name: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[ProviderSignal]:

        # 1. Prepare Payload
        ollama_messages = [
            {"role": m.role, "content": m.content, "images": m.metadata.get("images")}
            for m in messages
        ]

        try:
            # 2. Call SDK
            stream = await self.client.chat(
                model=model_name,
                messages=ollama_messages,
                tools=tools,
                stream=True,
                options={"num_predict": -1},
            )

            # 3. Map Stream
            async for chunk in stream:
                # A. Metrics (Done)
                if chunk.done:
                    metrics = {
                        "total_duration": chunk.total_duration,
                        "load_duration": chunk.load_duration,
                        "prompt_eval_count": chunk.prompt_eval_count,
                        "eval_count": chunk.eval_count,
                    }
                    yield ProviderSignal(type="metrics", data=metrics)
                    continue

                # B. Thinking (Reasoning Trace)
                if hasattr(chunk.message, "thinking") and chunk.message.thinking:
                    yield ProviderSignal(type="thinking", data=chunk.message.thinking)

                # C. Tool Calls
                # Ollama SDK aggregates tools in the final message or streams them.
                # If we see tool_calls, we assume they are fully formed objects in that chunk
                if chunk.message.tool_calls:
                    for tc in chunk.message.tool_calls:
                        # Convert Ollama Tool -> Monk ToolRequest
                        req = ToolRequest(
                            name=tc.function.name,
                            parameters=tc.function.arguments,
                            call_id=str(
                                time.time()
                            ),  # Ollama doesn't always give IDs in stream
                            requires_confirmation=False,  # Will be checked by registry
                        )
                        yield ProviderSignal(type="tool_call", data=req)

                # D. Content (Standard Text)
                if chunk.message.content:
                    yield ProviderSignal(type="content", data=chunk.message.content)

        except Exception as e:
            logger.error(f"Stream Error: {e}", exc_info=True)
            yield ProviderSignal(type="error", data=str(e))
            raise ProviderError(f"Ollama stream failed: {str(e)}")
