import asyncio
import json
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
            seen_tool_call_ids: Dict[str, int] = {}
            generated_tool_call_count = 0
            async for chunk in stream:
                msg = chunk.message
                # Handle content chunks
                content = msg.content if isinstance(msg.content, str) else None
                if content:
                    yield ProviderSignal(type="content", data=content)

                # Handle thinking chunks (supported by recent Ollama message schema).
                thinking = msg.thinking if isinstance(msg.thinking, str) else None
                if thinking:
                    yield ProviderSignal(type="thinking", data=thinking)

                # Handle tool calls when they appear
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = self._extract_tool_call_name(tc)
                        tool_arguments = self._extract_tool_call_arguments(tc)
                        raw_call_id = self._extract_tool_call_id(tc)
                        if not raw_call_id:
                            generated_tool_call_count += 1
                            raw_call_id = f"call_generated_{generated_tool_call_count}"
                            logger.warning(
                                "Ollama tool call '%s' was missing an id. Generated %s.",
                                tool_name or "<missing name>",
                                raw_call_id,
                            )
                        call_id, was_duplicate = self._normalize_tool_call_id(
                            raw_call_id, seen_tool_call_ids
                        )
                        if was_duplicate:
                            logger.warning(
                                "Ollama emitted duplicate tool call id '%s'. Normalized to '%s'.",
                                raw_call_id,
                                call_id,
                            )
                        if not tool_name:
                            logger.warning(
                                "Ollama tool call '%s' has no function name after normalization.",
                                call_id,
                            )
                        tool_metadata: Dict[str, Any] = {
                            "provider": "ollama",
                            "normalized_tool_call_id": call_id,
                            "provider_tool_call_id": raw_call_id,
                        }
                        if not tool_name:
                            tool_metadata["malformed_reason"] = "missing_tool_name"
                            tool_metadata["provider_raw_tool_call"] = self._to_serializable(
                                tc
                            )
                            tool_metadata["provider_raw_chunk"] = self._to_serializable(
                                chunk
                            )
                        # Convert Ollama Tool -> Monk ToolRequest
                        req = ToolRequest(
                            name=tool_name,
                            parameters=tool_arguments,
                            call_id=call_id,
                            requires_confirmation=False,
                            metadata=tool_metadata,
                        )
                        yield ProviderSignal(type="tool_call", data=req)

                # Handle final metrics when done
                if chunk.done:
                    metrics = {
                        "provider": "ollama",
                        "request_model": model_name,
                        "response_model": chunk.model,
                        "done_reason": chunk.done_reason,
                        "total_duration": chunk.total_duration,
                        "load_duration": chunk.load_duration,
                        "prompt_eval_count": chunk.prompt_eval_count,
                        "eval_count": chunk.eval_count,
                    }
                    yield ProviderSignal(type="metrics", data=metrics)

        except asyncio.CancelledError:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Ollama stream cancelled by caller.", exc_info=True)
            else:
                logger.info("Ollama stream cancelled by caller.")
            raise
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
                tool_calls = self._normalize_assistant_tool_calls(
                    metadata.get("tool_calls") or []
                )
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
    def _normalize_assistant_tool_calls(tool_calls: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for raw in tool_calls:
            if not isinstance(raw, dict):
                continue
            function = raw.get("function")
            if not isinstance(function, dict):
                continue

            name = str(function.get("name") or "").strip()
            if not name:
                continue

            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                text = arguments.strip()
                if not text:
                    parsed_args: Any = {}
                else:
                    try:
                        parsed_args = json.loads(text)
                    except json.JSONDecodeError:
                        parsed_args = {"value": arguments}
            elif isinstance(arguments, dict):
                parsed_args = arguments
            else:
                parsed_args = {"value": arguments}

            if not isinstance(parsed_args, dict):
                parsed_args = {"value": parsed_args}

            item: Dict[str, Any] = {
                "type": "function",
                "function": {"name": name, "arguments": parsed_args},
            }
            if raw.get("id"):
                item["id"] = str(raw["id"])
            normalized.append(item)
        return normalized

    @staticmethod
    def _extract_tool_call_id(tool_call: Any) -> Optional[str]:
        """
        Best-effort extraction of a provider-issued tool call id.
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

        return None

    @staticmethod
    def _extract_tool_call_name(tool_call: Any) -> str:
        function = getattr(tool_call, "function", None)
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        elif function is not None:
            name = getattr(function, "name", None)
            if isinstance(name, str) and name.strip():
                return name.strip()

        if isinstance(tool_call, dict):
            function_payload = tool_call.get("function")
            if isinstance(function_payload, dict):
                name = function_payload.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            direct_name = tool_call.get("name")
            if isinstance(direct_name, str) and direct_name.strip():
                return direct_name.strip()

        model_dump = getattr(tool_call, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                function_payload = dumped.get("function")
                if isinstance(function_payload, dict):
                    name = function_payload.get("name")
                    if isinstance(name, str) and name.strip():
                        return name.strip()
                direct_name = dumped.get("name")
                if isinstance(direct_name, str) and direct_name.strip():
                    return direct_name.strip()

        return ""

    @staticmethod
    def _extract_tool_call_arguments(tool_call: Any) -> Dict[str, Any]:
        arguments: Any = None

        function = getattr(tool_call, "function", None)
        if isinstance(function, dict):
            arguments = function.get("arguments")
        elif function is not None:
            arguments = getattr(function, "arguments", None)

        if arguments is None and isinstance(tool_call, dict):
            function_payload = tool_call.get("function")
            if isinstance(function_payload, dict):
                arguments = function_payload.get("arguments")
            elif "arguments" in tool_call:
                arguments = tool_call.get("arguments")

        if arguments is None:
            model_dump = getattr(tool_call, "model_dump", None)
            if callable(model_dump):
                dumped = model_dump()
                if isinstance(dumped, dict):
                    function_payload = dumped.get("function")
                    if isinstance(function_payload, dict):
                        arguments = function_payload.get("arguments")
                    elif "arguments" in dumped:
                        arguments = dumped.get("arguments")

        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            text = arguments.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                logger.warning(
                    "Ollama tool call arguments are not valid JSON; wrapping as string payload."
                )
                return {"value": arguments}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        return {"value": arguments}

    @staticmethod
    def _normalize_tool_call_id(
        base_call_id: str, seen_tool_call_ids: Dict[str, int]
    ) -> tuple[str, bool]:
        seen_count = seen_tool_call_ids.get(base_call_id, 0)
        seen_tool_call_ids[base_call_id] = seen_count + 1
        if seen_count == 0:
            return base_call_id, False
        return f"{base_call_id}__dup{seen_count}", True

    @staticmethod
    def _to_serializable(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): OllamaProvider._to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [OllamaProvider._to_serializable(item) for item in value]

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            return OllamaProvider._to_serializable(dumped)

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            dumped = to_dict()
            return OllamaProvider._to_serializable(dumped)

        as_dict = getattr(value, "__dict__", None)
        if isinstance(as_dict, dict):
            return {
                str(k): OllamaProvider._to_serializable(v)
                for k, v in as_dict.items()
                if not str(k).startswith("_")
            }

        return str(value)
