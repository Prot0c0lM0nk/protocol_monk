import time
import logging
from typing import AsyncIterator, List, Dict, Any, Optional, Set

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

        # SAFETY NOTE: We create ONE client here and reuse it.
        # This prevents opening thousands of connections.
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
        options: Optional[Dict[str, Any]] = None,  # [FIX] Accept options
    ) -> AsyncIterator[ProviderSignal]:

        # 1. Prepare Payload
        ollama_messages = self._serialize_messages(messages)

        try:
            # 2. Call SDK with streaming
            # We pass 'options' (temperature, etc.) directly to Ollama
            stream = await self.client.chat(
                model=model_name,
                messages=ollama_messages,
                tools=tools,
                options=options,  # [FIX] Pass options to SDK
                stream=True,
            )

            # 3. Process the streaming response
            async for chunk in stream:
                # Handle content chunks
                if chunk.message.content:
                    yield ProviderSignal(type="content", data=chunk.message.content)

                # Handle tool calls when they appear
                if chunk.message.tool_calls:
                    for tc in chunk.message.tool_calls:
                        call_id = self._extract_tool_call_id(tc)
                        # Convert Ollama Tool -> Monk ToolRequest
                        req = ToolRequest(
                            name=tc.function.name,
                            parameters=tc.function.arguments,
                            call_id=call_id,
                            requires_confirmation=False,
                        )
                        yield ProviderSignal(type="tool_call", data=req)

                # Handle final metrics when done
                if chunk.done:
                    metrics = {
                        "total_duration": chunk.total_duration,
                        "load_duration": chunk.load_duration,
                        "prompt_eval_count": chunk.prompt_eval_count,
                        "eval_count": chunk.eval_count,
                    }
                    yield ProviderSignal(type="metrics", data=metrics)

        except Exception as e:
            logger.error(f"Stream Error: {e}", exc_info=True)
            yield ProviderSignal(type="error", data=str(e))
            raise ProviderError(f"Ollama stream failed: {str(e)}")

    def _serialize_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """
        Convert internal message objects into Ollama chat payload format.

        Important:
        - Preserve assistant tool_calls when available.
        - Send tool-role messages as tool results only when they can be matched
          to a prior assistant tool_call id.
        - Fallback unmatched tool-role messages to plain assistant text to avoid
          provider-side tool-result id validation errors.
        """
        serialized: List[Dict[str, Any]] = []
        known_tool_call_ids: Set[str] = set()

        for message in messages:
            metadata = message.metadata or {}
            role = message.role
            payload: Dict[str, Any] = {"role": role, "content": message.content}

            images = metadata.get("images")
            if images is not None:
                payload["images"] = images

            if role == "assistant":
                tool_calls = metadata.get("tool_calls") or []
                if tool_calls:
                    payload["tool_calls"] = tool_calls
                    for tool_call in tool_calls:
                        if isinstance(tool_call, dict):
                            call_id = tool_call.get("id")
                            if call_id:
                                known_tool_call_ids.add(str(call_id))
                serialized.append(payload)
                continue

            if role == "tool":
                tool_name = metadata.get("tool_name")
                tool_call_id = metadata.get("tool_call_id")

                if tool_call_id and str(tool_call_id) in known_tool_call_ids:
                    if tool_name:
                        payload["tool_name"] = tool_name
                    payload["tool_call_id"] = str(tool_call_id)
                    serialized.append(payload)
                    continue

                # Fallback: retain content for model continuity without using tool role.
                fallback_text = (
                    f"[Tool Result: {tool_name or 'unknown'} | "
                    f"tool_call_id={tool_call_id or 'unmatched'}]\n{message.content}"
                )
                serialized.append({"role": "assistant", "content": fallback_text})
                continue

            serialized.append(payload)

        return serialized

    @staticmethod
    def _extract_tool_call_id(tool_call: Any) -> str:
        """
        Best-effort extraction of a provider-issued tool call id.
        Falls back to a generated id when missing.
        """
        direct_id = getattr(tool_call, "id", None)
        if direct_id:
            return str(direct_id)

        model_dump = getattr(tool_call, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict) and dumped.get("id"):
                return str(dumped["id"])

        if isinstance(tool_call, dict) and tool_call.get("id"):
            return str(tool_call["id"])

        return f"call_{int(time.time() * 1000)}"
