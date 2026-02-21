import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from protocol_monk.agent.structs import Message, ProviderSignal, ToolRequest
from protocol_monk.config.settings import Settings
from protocol_monk.exceptions.provider import ProviderError
from protocol_monk.providers.base import BaseProvider

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - handled at runtime in __init__
    AsyncOpenAI = None

logger = logging.getLogger("OpenRouterProvider")


class OpenRouterProvider(BaseProvider):
    """
    Adapter for OpenRouter using OpenAI-compatible chat-completions streaming.
    """

    def __init__(self, settings: Settings):
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.api_key = settings.openrouter_api_key

        if not self.api_key:
            raise ProviderError(
                "OPENROUTER_API_KEY is required when using OpenRouterProvider."
            )
        if AsyncOpenAI is None:
            raise ProviderError(
                "openai dependency is missing. Install requirements to use OpenRouter."
            )

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def validate_connection(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception as exc:
            logger.error("OpenRouter connection failed: %s", exc)
            return False

    async def stream_chat(
        self,
        messages: List[Message],
        model_name: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[ProviderSignal]:
        payload_messages = self._serialize_messages(messages)
        request_options = self._sanitize_options(options or {})

        request_payload: Dict[str, Any] = {
            "model": model_name,
            "messages": payload_messages,
            "tools": tools or [],
            "stream": True,
            # Requests usage on streamed responses when provider supports it.
            "stream_options": {"include_usage": True},
        }
        request_payload.update(request_options)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "OpenRouter request headers: %s",
                {"Authorization": "Bearer ***REDACTED***"},
            )
            logger.debug(
                "OpenRouter request payload: %s",
                json.dumps(request_payload, ensure_ascii=False, default=str),
            )

        pending_tool_calls: Dict[int, Dict[str, Any]] = {}
        telemetry: Dict[str, Any] = {
            "provider": "openrouter",
            "request_model": model_name,
            "base_url": self.base_url,
            "chunk_count": 0,
            "usage": {},
            "finish_reasons": [],
        }
        last_chunk: Dict[str, Any] = {}

        try:
            stream = await self.client.chat.completions.create(**request_payload)

            async for chunk in stream:
                chunk_data = self._to_dict(chunk)
                telemetry["chunk_count"] += 1
                last_chunk = chunk_data

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "OpenRouter chunk payload: %s",
                        json.dumps(chunk_data, ensure_ascii=False, default=str),
                    )

                if chunk_data.get("id"):
                    telemetry["id"] = chunk_data["id"]
                if chunk_data.get("model"):
                    telemetry["model"] = chunk_data["model"]
                if chunk_data.get("created"):
                    telemetry["created"] = chunk_data["created"]

                usage = chunk_data.get("usage")
                if isinstance(usage, dict) and usage:
                    telemetry["usage"] = usage

                choices = chunk_data.get("choices") or []
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue

                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        telemetry["finish_reasons"].append(str(finish_reason))

                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield ProviderSignal(type="content", data=content)
                    elif isinstance(content, list):
                        extracted = self._extract_content_parts(content)
                        if extracted:
                            yield ProviderSignal(type="content", data=extracted)

                    self._merge_tool_call_chunks(
                        pending_tool_calls, delta.get("tool_calls") or []
                    )

                    if finish_reason == "tool_calls":
                        for req in self._flush_ready_tool_calls(pending_tool_calls):
                            yield ProviderSignal(type="tool_call", data=req)
                        pending_tool_calls.clear()

            # Flush remaining calls at stream end (if provider omitted finish_reason).
            for req in self._flush_ready_tool_calls(pending_tool_calls):
                yield ProviderSignal(type="tool_call", data=req)

            telemetry["final_chunk"] = last_chunk
            yield ProviderSignal(type="metrics", data=telemetry)

        except Exception as exc:
            msg = self._format_provider_error(exc)
            logger.error("OpenRouter stream failed: %s", msg, exc_info=True)
            yield ProviderSignal(type="error", data=msg)
            raise ProviderError(msg)

    @staticmethod
    def _to_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            dumped = to_dict()
            if isinstance(dumped, dict):
                return dumped
        return {}

    @staticmethod
    def _extract_content_parts(parts: List[Any]) -> str:
        content_chunks: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and part.get("text"):
                content_chunks.append(str(part["text"]))
        return "".join(content_chunks)

    def _merge_tool_call_chunks(
        self, pending: Dict[int, Dict[str, Any]], tool_calls: List[Any]
    ) -> None:
        for item in tool_calls:
            if not isinstance(item, dict):
                continue
            index = int(item.get("index", 0) or 0)
            slot = pending.setdefault(
                index, {"id": None, "name": None, "arguments_parts": []}
            )
            if item.get("id"):
                slot["id"] = str(item["id"])
            function = item.get("function") or {}
            if isinstance(function, dict):
                if function.get("name"):
                    slot["name"] = str(function["name"])
                arguments = function.get("arguments")
                if arguments:
                    slot["arguments_parts"].append(str(arguments))

    def _flush_ready_tool_calls(
        self, pending: Dict[int, Dict[str, Any]]
    ) -> List[ToolRequest]:
        ready: List[ToolRequest] = []
        for index in sorted(pending.keys()):
            entry = pending[index]
            name = entry.get("name")
            if not name:
                continue

            arguments_text = "".join(entry.get("arguments_parts", [])).strip()
            parsed_args = self._parse_tool_arguments(arguments_text)
            if parsed_args is None:
                logger.warning(
                    "Skipping OpenRouter tool call '%s' due to invalid JSON arguments.",
                    name,
                )
                continue

            call_id = entry.get("id") or f"call_{int(time.time() * 1000)}_{index}"
            ready.append(
                ToolRequest(
                    name=name,
                    parameters=parsed_args,
                    call_id=str(call_id),
                    requires_confirmation=False,
                )
            )
        return ready

    @staticmethod
    def _parse_tool_arguments(arguments_text: str) -> Optional[Dict[str, Any]]:
        if not arguments_text:
            return {}
        try:
            parsed = json.loads(arguments_text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        # Tool schema expects object arguments.
        return {"value": parsed}

    @staticmethod
    def _sanitize_options(options: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(options, dict):
            return {}

        allowed = {
            "temperature",
            "top_p",
            "max_tokens",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "stop",
            "n",
            "tool_choice",
            "parallel_tool_calls",
            "response_format",
        }
        cleaned: Dict[str, Any] = {k: v for k, v in options.items() if k in allowed}
        if "max_tokens" not in cleaned and "num_predict" in options:
            cleaned["max_tokens"] = options["num_predict"]
        return cleaned

    @staticmethod
    def _normalize_assistant_tool_calls(tool_calls: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for raw in tool_calls:
            if not isinstance(raw, dict):
                continue
            function = raw.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not name:
                continue
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments_text = arguments
            else:
                arguments_text = json.dumps(arguments, ensure_ascii=False, default=str)
            item: Dict[str, Any] = {
                "type": "function",
                "function": {"name": str(name), "arguments": arguments_text},
            }
            if raw.get("id"):
                item["id"] = str(raw["id"])
            normalized.append(item)
        return normalized

    def _serialize_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """
        Convert internal message objects into OpenAI-compatible payload format.

        Important:
        - Preserve assistant tool_calls metadata.
        - Send tool-role messages only when they can be matched to known call ids.
        - Fallback unmatched tool-role messages to assistant text to avoid
          tool-call-id validation errors.
        """
        serialized: List[Dict[str, Any]] = []
        known_tool_call_ids: Set[str] = set()

        for message in messages:
            metadata = message.metadata or {}
            role = message.role
            content = message.content or ""

            if role == "assistant":
                payload: Dict[str, Any] = {"role": "assistant", "content": content}
                tool_calls = self._normalize_assistant_tool_calls(
                    metadata.get("tool_calls") or []
                )
                if tool_calls:
                    payload["tool_calls"] = tool_calls
                    for tool_call in tool_calls:
                        if tool_call.get("id"):
                            known_tool_call_ids.add(str(tool_call["id"]))
                serialized.append(payload)
                continue

            if role == "tool":
                tool_name = metadata.get("tool_name")
                tool_call_id = metadata.get("tool_call_id")

                if tool_call_id and str(tool_call_id) in known_tool_call_ids:
                    serialized.append(
                        {
                            "role": "tool",
                            "content": content,
                            "tool_call_id": str(tool_call_id),
                        }
                    )
                    continue

                fallback_text = (
                    f"[Tool Result: {tool_name or 'unknown'} | "
                    f"tool_call_id={tool_call_id or 'unmatched'}]\n{content}"
                )
                serialized.append({"role": "assistant", "content": fallback_text})
                continue

            serialized.append({"role": role, "content": content})

        return serialized

    @staticmethod
    def _format_provider_error(exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        body = getattr(exc, "body", None)
        if body is None:
            response = getattr(exc, "response", None)
            body = getattr(response, "text", None) if response is not None else None
            if callable(body):
                try:
                    body = body()
                except Exception:
                    body = None

        snippet = ""
        if body is not None:
            snippet = str(body)[:600]

        if status_code is None:
            return f"OpenRouter request failed: {exc}"

        status_code = int(status_code)
        reason = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            429: "rate_limited",
        }.get(status_code, "api_error")
        if snippet:
            return (
                f"OpenRouter API error ({status_code} {reason}). "
                f"Response snippet: {snippet}"
            )
        return f"OpenRouter API error ({status_code} {reason})."
