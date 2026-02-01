"""
Streaming Logic
===============
Handles model stream iteration and error mapping.
"""

import asyncio
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from agent.events import AgentEvents, EventBus
from exceptions import ModelRateLimitError, ModelResponseParseError

logger = logging.getLogger(__name__)


class ResponseStreamHandler:
    """Manages the streaming connection to the model."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    async def stream(
        self,
        model_client,
        context: List[Dict],
        tools_schema: Optional[List[Dict]] = None,
        retry_count: int = 0,
    ) -> Any:
        """
        Yields chunks and returns the final full response object.
        Emits events for thinking and text chunks.
        """
        await self.event_bus.emit(AgentEvents.THINKING_STARTED.value, {})

        accumulated_text = ""
        tool_calls_accumulator = None

        try:
            async for chunk in model_client.get_response_async(
                context, stream=True, tools=tools_schema
            ):
                # 1. Handle Thinking
                if isinstance(chunk, dict) and chunk.get("type") == "thinking":
                    await self.event_bus.emit(
                        AgentEvents.STREAM_CHUNK.value, {"thinking": chunk["content"]}
                    )
                    continue

                # 2. Handle Text
                if isinstance(chunk, str):
                    accumulated_text += chunk
                    await self.event_bus.emit(
                        AgentEvents.STREAM_CHUNK.value, {"chunk": chunk}
                    )

                # 3. Handle Tool Objects (Ollama/Dicts)
                elif (
                    hasattr(chunk, "message")
                    or isinstance(chunk, dict)
                    or isinstance(chunk, list)
                ):
                    # Simple accumulation for non-streaming objects,
                    # or complex merge for streaming dicts (handled by caller or simplified here)
                    # For simplicity in this refactor, we assume the Client handles the heavy lifting
                    # or we capture the object directly if it's a final object.
                    if isinstance(chunk, dict) and "tool_calls" in chunk:
                        # This is likely a stream chunk for tools
                        from agent.logic.parsers import ModelResponseParser

                        tool_calls_accumulator = (
                            ModelResponseParser.merge_tool_call_chunks(
                                tool_calls_accumulator, chunk
                            )
                        )
                    else:
                        # Full object replacement (Ollama)
                        tool_calls_accumulator = chunk

            # Return the final result
            if tool_calls_accumulator:
                return tool_calls_accumulator
            return accumulated_text

        except ModelRateLimitError as e:
            MAX_RETRIES = 3
            if retry_count >= MAX_RETRIES:
                await self.event_bus.emit(
                    AgentEvents.ERROR.value,
                    {
                        "message": "Max retries exceeded for rate limit",
                        "context": "rate_limit",
                    },
                )
                return "Rate limit retries exceeded."
            await self.event_bus.emit(
                AgentEvents.WARNING.value,
                {"message": e.user_hint, "context": "rate_limit"},
            )
            await asyncio.sleep(e.retry_after)
            # Recursive retry with increment
            return await self.stream(
                model_client, context, tools_schema, retry_count + 1
            )

        except Exception as e:
            logger.exception("Stream error")
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {"message": "Model stream failed.", "context": "stream_error"},
            )
            return "Error during generation."

        finally:
            await self.event_bus.emit(AgentEvents.THINKING_STOPPED.value, {})
